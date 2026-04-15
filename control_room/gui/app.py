from dash import Dash

from control_room.gui.callbacks import add_callbacks
from control_room.gui.layout import get_layout
from control_room.utils.modules import ControlRoomModuleConnection


def build_app(modules: list[ControlRoomModuleConnection], macros: dict | None) -> Dash:
    """
    Build and configure a Dash web application for the control room.

    This function initializes a Dash application, sets up the layout, and attaches
    callbacks to handle user interactions. It returns the configured Dash app.

    Parameters
    ----------
    modules : list[ControlRoomModuleConnection]
        A list of ControlRoomModuleConnection objects representing the modules to be included
        in the application.
    macros : dict | None
        A dictionary containing macro definitions to be used in the application.
        If None, no macros are used.

    Returns
    -------
    Dash
        The configured Dash application.
    """
    app = Dash(__name__, external_stylesheets=["assets/styles.css"])
    app.layout = get_layout(modules, macros=macros)

    # attach callbacks
    app = add_callbacks(app, modules=modules, macros=macros)

    return app
