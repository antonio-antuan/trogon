from __future__ import annotations

import itertools
import shlex
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, List, Optional

from rich.text import Text

from textual_click.introspect import (
    CommandSchema,
    CommandName,
    OptionSchema,
    ArgumentSchema,
    MultiValueParamData,
)
from textual_click.widgets.parameter_controls import ValueNotSupplied


@dataclass
class UserOptionData:
    """
    A dataclass to store user input for a specific option.

    Attributes:
        name: The name of the option.
        value: The user-provided value for the option.
        option_schema: The schema corresponding to this option.
    """

    name: str | list[str]
    value: tuple[Any]  # Multi-value options will be tuple length > 1
    option_schema: OptionSchema

    @property
    def string_name(self) -> str:
        if isinstance(self.name, str):
            return self.name
        else:
            return self.name[0]


@dataclass
class UserArgumentData:
    """
    A dataclass to store user input for a specific argument.

    Attributes:
        name: The name of the argument.
        value: The user-provided value for the argument.
        argument_schema: The schema corresponding to this argument.
    """

    name: str
    value: Any
    argument_schema: ArgumentSchema


@dataclass
class UserCommandData:
    """
    A dataclass to store user input for a command, its options, and arguments.

    Attributes:
        name: The name of the command.
        options: A list of UserOptionData instances representing the user input for the command's options.
        arguments: A list of UserArgumentData instances representing the user input for the command's arguments.
        subcommand: An optional UserCommandData instance representing a subcommand of the current command.
            Since commands can be nested (i.e. subcommands), this may be processed recursively.
    """

    name: CommandName
    options: List[UserOptionData]
    arguments: List[UserArgumentData]
    subcommand: Optional["UserCommandData"] = None
    parent: Optional["UserCommandData"] = None
    command_schema: Optional["CommandSchema"] = None

    def to_cli_args(self) -> List[str]:
        """
        Generates a list of strings representing the CLI invocation based on the user input data.

        Returns:
            A list of strings that can be passed to subprocess.run to execute the command.
        """
        args = [self.name]

        multiples = defaultdict(list)
        multiples_schemas = {}

        for option in self.options:
            if option.option_schema.multiple:
                # We need to gather the items for the same option,
                #  compare them to the default, then display them all
                #  if they aren't equivalent to the default.
                multiples[option.string_name].append(option.value)
                multiples_schemas[option.string_name] = option.option_schema
            else:
                value_data: list[tuple[Any]] = [option.value]
                default_data: list[tuple[Any]] = option.option_schema.default.values

                flattened_values = sorted(itertools.chain.from_iterable(value_data))
                flattened_defaults = sorted(itertools.chain.from_iterable(default_data))

                # TODO: We need to improve handling of empty strings to differentiate
                #  between a value that hasn't been supplied and an actual empty string.
                #  When we retrieve the value from the input, if the user wants empty str
                #  (i.e. the user has checked a checkbox saying so), then we should pass
                #  up the empty string, otherwise we should pass up None.

                # If the user has supplied values (any values are not None), then
                # we don't display the value.
                values_supplied = any(
                    value != ValueNotSupplied() for value in flattened_values)
                values_are_defaults = list(map(str, flattened_values)) == list(
                    map(str, flattened_defaults)
                )

                # If the user has supplied values, and they're not the default values,
                # then we want to display them in the command string...
                if values_supplied and not values_are_defaults:
                    if isinstance(option.name, str):
                        args.append(option.name)
                    else:
                        # Use the option with the longest name, since
                        # it's probably the most descriptive (use --verbose over -v)
                        longest_name = max(option.name, key=len)
                        args.append(longest_name)

                    # Only add a value for non-boolean options
                    is_true_bool = value_data == [(True,)]
                    this_value_supplied = value_data != ValueNotSupplied()
                    if this_value_supplied or is_true_bool:
                        if isinstance(value_data, tuple):
                            args.extend(str(v) for v in value_data)
                        else:
                            args.append(str(value_data))

        for option_name, values in multiples.items():
            # Check if the values given for this option differ from the default
            defaults = multiples_schemas[option_name].default or []
            sorted_supplied_values = list(sorted(itertools.chain.from_iterable(values)))
            sorted_default_values = list(
                sorted(itertools.chain.from_iterable(defaults.values))
            )

            supplied_values = list(map(str, sorted_supplied_values))
            supplied_defaults = list(map(str, sorted_default_values))
            values_are_defaults = supplied_values == supplied_defaults
            values_supplied = any(
                value != ValueNotSupplied() for value in sorted_supplied_values)

            # If the user has supplied any non-default values, include them...
            if values_supplied and not values_are_defaults:
                for value_data in values:
                    if value_data != ValueNotSupplied():
                        args.append(option_name)
                        print(f"Adding {value_data}")
                        args.extend(str(v) for v in value_data)

        for argument in self.arguments:
            value_data = argument.value
            for argument_value in value_data:
                if argument_value != ValueNotSupplied():
                    args.append(argument_value)

        if self.subcommand:
            args.extend(self.subcommand.to_cli_args())

        return args

    def to_cli_string(self, include_root_command: bool = False) -> Text:
        """
        Generates a string representing the CLI invocation as if typed directly into the
        command line.

        Returns:
            A string representing the command invocation.
        """
        args = self.to_cli_args()
        if not include_root_command:
            args = args[1:]
        return Text(" ").join(Text(shlex.quote(arg)) for arg in args if not arg == ValueNotSupplied())

    def fill_defaults(self, command_schema: CommandSchema) -> None:
        """
        Prefills the UserCommandData instance with default values for options and
        arguments based on the provided CommandSchema.

        Args:
            command_schema: A CommandSchema instance representing the schema for
                the command to prefill defaults.
        """
        # Prefill default option values
        for option_schema in command_schema.options:
            default = option_schema.default
            if default is not None and not any(
                opt.name == option_schema.name for opt in self.options
            ):
                # There's a separate UserOptionData instance for each instance of an
                # option passed. So `--path . --path src` would be 2 UserOptionData
                # objects. If multiple=True, there'll be many instances. If
                # multiple=False, then we expect that only a single UserOptionData
                # will be appended here.
                for value in default.values:
                    self.options.append(
                        UserOptionData(
                            name=option_schema.name,
                            value=value,
                            option_schema=option_schema,
                        )
                    )

        # Prefill default argument values
        for arg_schema in command_schema.arguments:
            if arg_schema.default is not None and not any(
                arg.name == arg_schema.name for arg in self.arguments
            ):
                self.arguments.append(
                    UserArgumentData(
                        name=arg_schema.name,
                        value=arg_schema.default,
                        argument_schema=arg_schema,
                    )
                )

        # Prefill defaults for subcommand if present
        if self.subcommand:
            subcommand_schema = next(
                (
                    cmd
                    for cmd in command_schema.subcommands.values()
                    if cmd.name == self.subcommand.name
                ),
                None,
            )
            if subcommand_schema:
                self.subcommand.fill_defaults(subcommand_schema)
