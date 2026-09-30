// Hand-rolled drag-to-resize for the layout dividers. Uses event
// delegation on `document` since Dash re-renders the divider elements.
(function () {
  const DIVIDERS = {
    x_divider: {
      axis: "x",
      containerId: "control_room_body",
      paneId: "lsl_and_log_div",
    },
    y_divider_left: {
      axis: "y",
      containerId: "lsl_and_log_div",
      paneId: "lsl_stream_tile",
    },
    y_divider_right: {
      axis: "y",
      containerId: "module_tile_div",
      paneId: "macros_div",
    },
  };

  let dragging = null;

  // Returns a part/whole * 100%, clipped to [15%, 85%]
  function pct(part, whole) {
    return Math.min(85, Math.max(15, (part / whole) * 100));
  }

  document.addEventListener("mousedown", function (e) {
    const descriptor = DIVIDERS[e.target.id];
    if (descriptor) {
      dragging = descriptor;
      e.preventDefault();
    }
  });

  document.addEventListener("mousemove", function (e) {
    if (!dragging) return;

    const container = document.getElementById(dragging.containerId);
    const pane = document.getElementById(dragging.paneId);
    const rect = container.getBoundingClientRect();

    if (dragging.axis === "x") {
      pane.style.flexBasis = `${pct(e.clientX - rect.left, rect.width)}%`;
    } else {
      pane.style.flexBasis = `${pct(e.clientY - rect.top, rect.height)}%`;
    }
  });

  document.addEventListener("mouseup", function () {
    dragging = null;
  });
})();
