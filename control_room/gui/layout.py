import json

from dash import dcc, html

from control_room.callbacks import is_ao_module

# from control_room.utils.logging import logger
from control_room.utils.logserver import logfile as log_file_path
from control_room.utils.modules import ControlRoomModuleConnection

# Default layout state for the control room GUI.
# Horizontally, the GUI is split into two sections, which each have a vertical split.
# The left side contains the LSL streams and the log file, while the right side contains the macros and module tiles.
# The layout state is defined in terms of percentages of the total width/height
DEFAULT_LAYOUT_STATE = {
    "x_div": 50,
    "y_div_left": 50,
    "y_div_right": None,  # Automatically sized to content if not specified
}


def get_layout(
    modules: list[ControlRoomModuleConnection],
    macros: dict | None,
    layout_cfg: dict | None = None,
) -> html.Div:
    """
    Generate the layout for the control room application.

    This function creates the overall layout of the control room application,
    including headers, module tiles, and other UI components. It integrates
    modules and macros into the layout.

    Parameters
    ----------
    modules : list[ControlRoomModuleConnection]
        A list of ControlRoomModuleConnection objects representing the modules to be included
        in the application.
    macros : dict | None
        A dictionary containing macro definitions to be used in the application.
        If None, no macros are used.
    layout_cfg : dict | None
        Optional configuration dictionary from the config file, giving the initial
        pane-size ratios. Falls back to a hardcoded default if not given.

    Returns
    -------
    html.Div
        A Dash HTML Div containing the entire layout of the control room application.
    """
    logfile = log_file_path.stem + log_file_path.suffix

    module_tiles = [get_module_tile_layout(mod) for mod in modules]

    # Override the default layout state with any provided configuration
    layout_state = {**DEFAULT_LAYOUT_STATE}
    if layout_cfg is not None:
        layout_state.update(layout_cfg)

    if macros is not None:
        right_col = [
            create_macro_tile(macros, height=layout_state.get("y_div_right")),
            html.Div(id="y_divider_right"),
            html.Div(
                id="modules_pane",
                children=module_tiles,
            ),
        ]
    else:
        right_col = [html.Div(id="modules_pane", children=module_tiles)]

    return html.Div(
        id="control_room_app",
        children=[
            html.Div(
                id="header_row",
                children=[
                    html.Img(
                        src="assets/images/connection-box-chart-svgrepo-com.svg",  # noqa
                        id="control_room_icon",
                        className="header_icon",
                    ),
                    html.Div("DAREPLANE Control Room", id="control_room_title"),
                    html.Div(
                        children=[create_module_server_info(m) for m in modules],
                        id="module_server_check_boxes",
                    ),
                ],
            ),
            html.Div(
                id="control_room_body",
                children=[
                    # left side
                    html.Div(
                        id="lsl_and_log_div",
                        className="lsl_and_log",
                        style={"flexBasis": f"{layout_state['x_div']}%"}
                        if layout_state["x_div"] is not None
                        else {},
                        children=[
                            get_lsl_streams_tile(height=layout_state["y_div_left"]),
                            html.Div(id="y_divider_left"),
                            get_log_stream_tile(
                                logfile_name=logfile, height=None
                            ),  # Automatically sized to fill remaining space
                        ],
                    ),
                    html.Div(id="x_divider"),
                    # right side
                    html.Div(
                        id="module_tile_div",
                        className="module_tiles",
                        children=right_col,
                    ),
                    # A timer for the log reading and the lsl fetch
                    dcc.Interval(id="interval_3s", interval=3 * 1000, n_intervals=0),
                ],
            ),
            html.Div(id="last_pcomm_sent_div", className="hidden_div"),
            html.Div(id="last_macro_sent_div", className="hidden_div"),
        ],
    )


def create_module_server_info(module: ControlRoomModuleConnection) -> html.Div:
    # this will contain a parent box which is displayed in the header row
    # and some meta info text box, which is displayed only on hover

    return html.Div(
        children=[html.Div(str(module), className="module_meta")],
        className="module_check_box",
        id=f"{module.name}_check_box",
    )


def create_macro_tile(macros: dict, height: float | None) -> html.Div:
    """
    Create a tile containing buttons for each macro.

    This function generates a Dash HTML Div that includes a button for each macro
    defined in the provided dictionary. Each button is labeled with the macro's name
    and is part of a tile layout.

    Parameters
    ----------
    macros : dict
        A dictionary containing macro definitions. Each key-value pair in the dictionary
        represents a macro, where the key is the macro name and the value is a dictionary
        containing macro-specific configurations.
    height : float | None
        Optional height for the tile. If None, the height will be automatically sized.

    Returns
    -------
    html.Div
        A Dash HTML Div containing a tile with buttons for each macro.
    """
    layout = html.Div(
        id="macros_div",
        className="module_tile",
        style={"flexBasis": f"{height}%"} if height is not None else {},
        children=[
            # the header row
            html.Div(
                className="tile_header",
                children=[html.Div(className="module_name", children=["Macros"])],
            ),
            html.Div(
                className="tile_pcomms",
                children=[
                    get_macro_button_input_pair(mc)
                    for k, mc in macros.items()
                    if k != "globals"
                ],
            ),
        ],
    )

    return layout


def get_macro_button_input_pair(mc: dict) -> html.Div:
    """
    Create a macro button and input pair for a given macro configuration.

    This function generates a Dash HTML Div containing a button and an input field
    for a specified macro. The button is labeled with the macro's name, and the
    input field is pre-filled with a default JSON value if provided in the macro
    configuration.

    Parameters
    ----------
    mc : dict
        A dictionary containing the macro configuration. The dictionary should have
        the following structure:
        {
            "name": str,
            "default_json": dict | None
        }

    Returns
    -------
    html.Div
        A Dash HTML Div containing a button and an input field for the macro.
    """
    default_input = ""

    print(f"\n\n {mc} \n\n")

    if "default_json" in mc.keys():
        default_input = json.dumps(mc["default_json"])

    return html.Div(
        id=f"{mc['name']}|button_input_div",
        className="pcomm_button_input_row",
        children=[
            html.Button(
                f"{mc['name']}",
                id=f"{mc['name']}|button",
                className="pcomm_button",
                n_clicks=0,
            ),
            dcc.Textarea(id=f"{mc['name']}|input", value=default_input),
        ],
    )


def get_lsl_streams_tile(height: float | None) -> html.Div:
    """
    Create the tile showing the active LSL streams
    """
    return html.Div(
        id="lsl_stream_tile",
        className="tile",
        style={"flexBasis": f"{height}%"} if height is not None else {},
        children=[
            html.Div(
                children=[
                    html.Img(
                        src="assets/images/flows-1-svgrepo-com.svg",
                        className="header_icon",
                        id="lsl_title_icon",
                    ),
                    html.Div(
                        "LSL Streams",
                        id="lsl_streams_title",
                        className="tile_header",
                    ),
                ],
                id="lsl_tile_header",
            ),
            html.Div(id="lsl_streams_list"),
        ],
    )


def get_log_stream_tile(logfile_name: str, height: float | None) -> html.Div:
    """
    Create the tile showing the last lines of the log file
    """
    return html.Div(
        id="log_stream_tile",
        className="tile",
        style={"flexBasis": f"{height}%"} if height is not None else {},
        children=[
            html.Div(
                children=[
                    html.Img(
                        src="assets/images/log-file-format-svgrepo-com.svg",
                        className="header_icon",
                        id="logfile_title_icon",
                    ),
                    html.Div(
                        f"Logfile - {logfile_name}",
                        id="logfile_title",
                        className="tile_header",
                    ),
                ],
                id="log_stream_tile_header",
            ),
            html.Div(id="logfile_data"),
        ],
    )


def get_module_tile_layout(module: ControlRoomModuleConnection) -> html.Div:
    """
    Create the tile showing the individual modules
    """
    return html.Div(
        id=f"{module.name}_tile",
        className="module_tile tile",
        children=[
            # the header row
            html.Div(
                className="tile_header",
                children=[
                    html.Div(className="module_name", children=[f"{module.name}"]),
                ],
            ),
            # the pcommand button input pairs
            html.Div(
                className="tile_pcomms",
                children=[
                    get_pcomm_button_input_pair(pc, module.name, module)
                    for pc in module.gui_pcomms
                ],
            ),
        ],
    )


def get_pcomm_button_input_pair(
    pcomm_name: str, mod_name: str, conn: ControlRoomModuleConnection
) -> html.Div:
    """
    Create pairs of buttons and inputs for each pcommand
    """
    # logger.debug(f"Building button input for {pcomm_name=} {mod_name=}")
    defaults = ""
    if is_ao_module(mod_name):
        defaults = conn.pcomms_defaults[pcomm_name]

    return html.Div(
        id=f"{mod_name}|{pcomm_name}|button_input_div",
        className="pcomm_button_input_row",
        children=[
            html.Button(
                f"{pcomm_name}",
                id=f"{mod_name}|{pcomm_name}|button",
                className="pcomm_button",
                n_clicks=0,
            ),
            dcc.Textarea(
                id=f"{mod_name}|{pcomm_name}|input",
                className="module_input",
                value=defaults,
            ),
        ],
    )
