from __future__ import annotations

import dataclasses
from typing import Iterable, Any, Sized

from textual.app import ComposeResult
from textual.containers import VerticalScroll, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

from textual_click.introspect import (
    CommandSchema,
    CommandName,
    ArgumentSchema,
    OptionSchema,
)
from textual_click.run_command import UserCommandData, UserOptionData, UserArgumentData
from textual_click.widgets.parameter_controls import ParameterControls


@dataclasses.dataclass
class FormControlMeta:
    widget: Widget
    meta: OptionSchema | ArgumentSchema


class CommandForm(Widget):
    """Form which is constructed from an introspected Click app. Users
    make use of this form in order to construct CLI invocation strings."""

    DEFAULT_CSS = """
    .command-form-heading {
        padding: 1 0 0 2;
        text-style: u;
        color: $text 70%;
    }
    .command-form-input {
        margin: 0 1 0 1;
    }
    .command-form-label {
        padding: 1 0 0 2;
    }
    .command-form-radioset {
        margin: 0 0 0 2;
    }
    .command-form-multiple-choice {
        margin: 0 0 0 2;
    }
    .command-form-checkbox {
        padding: 1 0 0 2;
    }
    .command-form-command-group {
        margin: 1 2;
        height: auto;
        background: $boost;
        border: panel $primary 60%;
        border-title-color: $text 80%;
        border-title-style: bold;
        border-subtitle-color: $text 30%;
        padding-bottom: 1;
    }
    .command-form-control-help-text {
        margin: 0 0 0 2;
        height: auto;
        color: $text 40%;
    }
    """

    class Changed(Message):
        def __init__(self, command_data: UserCommandData):
            super().__init__()
            self.command_data = command_data
            """The new data taken from the form to be converted into a CLI invocation."""

    def __init__(
        self,
        command_schema: CommandSchema | None = None,
        command_schemas: dict[CommandName, CommandSchema] | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ):
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.command_schema = command_schema
        self.command_schemas = command_schemas

    def compose(self) -> ComposeResult:
        path_from_root = iter(self.command_schema.path_from_root)
        command_node = next(path_from_root)
        with VerticalScroll() as vs:
            vs.can_focus = False
            while command_node is not None:
                options = command_node.options
                arguments = command_node.arguments
                if options or arguments:
                    with Vertical(classes="command-form-command-group") as v:
                        is_inherited = command_node is not self.command_schema
                        v.border_title = (
                            f"{'↪ ' if is_inherited else ''}{command_node.name}"
                        )
                        v.border_subtitle = f"{'(parameters inherited from parent)' if is_inherited else ''}"
                        if arguments:
                            yield Label(f"Arguments", classes="command-form-heading")
                            for argument in arguments:
                                yield ParameterControls(argument, id=argument.key)

                        if options:
                            yield Label(f"Options", classes="command-form-heading")
                            for option in options:
                                yield ParameterControls(option, id=option.key)

                command_node = next(path_from_root, None)

    def on_mount(self) -> None:
        self._form_changed()

    def on_input_changed(self) -> None:
        self._form_changed()

    def on_radio_set_changed(self) -> None:
        self._form_changed()

    def on_checkbox_changed(self) -> None:
        self._form_changed()

    def on_multiple_choice_changed(self) -> None:
        self._form_changed()

    def _form_changed(self) -> UserCommandData:
        """Take the current state of the form and build a UserCommandData from it,
        then post a FormChanged message"""

        command_schema = self.command_schema
        path_from_root = command_schema.path_from_root

        # Sentinel root value to make constructing the tree a little easier.
        parent_command_data = UserCommandData(
            name=CommandName("_"), options=[], arguments=[]
        )

        root_command_data = parent_command_data
        try:
            for command in path_from_root:
                option_datas = []
                # For each of the options in the schema for this command,
                # lets grab the values the user has supplied for them in the form.
                for option in command.options:
                    parameter_control = self.query_one(
                        f"#{option.key}", ParameterControls
                    )
                    print(f"param {option.name}")
                    value = parameter_control.get_values()
                    for v in value.values:
                        option_data = UserOptionData(option.name, v, option)
                        option_datas.append(option_data)

                # Now do the same for the arguments
                argument_datas = []
                for argument in command.arguments:
                    form_control_widget = self.query_one(
                        f"#{argument.key}", ParameterControls
                    )
                    value = form_control_widget.get_values()
                    for v in value.values:
                        argument_data = UserArgumentData(argument.name, v, argument)
                        argument_datas.append(argument_data)

                command_data = UserCommandData(
                    name=command.name,
                    options=option_datas,
                    arguments=argument_datas,
                    parent=parent_command_data,
                    command_schema=command,
                )
                parent_command_data.subcommand = command_data
                parent_command_data = command_data
        except Exception as e:
            # TODO
            print(f"exception {e}")
            return
            # raise e

        # Trim the sentinel
        root_command_data = root_command_data.subcommand
        root_command_data.parent = None
        root_command_data.fill_defaults(self.command_schema)
        self.post_message(self.Changed(root_command_data))

    def focus(self, scroll_visible: bool = True):
        return self.first_control.focus()