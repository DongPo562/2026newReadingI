# Floating UI Refinements Report

## Overview
I have implemented the requested changes to the floating UI's behavior, layout, and persistence.

## Changes Implemented

1.  **Scrollbars & Dimensions**:
    *   **Horizontal Scrollbar**: Permanently disabled. The list width is fixed to the `panel_width` (240px) and will not expand with content.
    *   **Panel Height**: The panel now always opens to the fixed `panel_max_height` (360px), regardless of content size.
    *   **Vertical Scrollbar**: Automatically appears when the list content exceeds the fixed height.

2.  **Context Menus**:
    *   **List Items**: Removed the right-click context menu from individual file items.
    *   **Floating Ball**: Retained the right-click menu (Refresh, Exit) on the green ball.

3.  **Persistent Positioning**:
    *   **Logic**: The application now saves the floating ball's screen coordinates (`x, y`) to `config.ini` whenever you release the mouse after dragging.
    *   **Startup**: On launch, it checks `config.ini` for a saved position. If found, it restores it. If not (first run), it defaults to the middle-right of the screen.
    *   **Config**: Added `last_position` field to `config.ini`.

## Files Updated
*   `config.ini`: Added `last_position` field.
*   `config_loader.py`: Added logic to read/write `last_position`.
*   `floating_ui.py`:
    *   Modified `ListPanel` to disable horizontal scrolling and use fixed height.
    *   Removed `contextMenuEvent` from `AudioListItem`.
    *   Updated `FloatingBall` to save position on `mouseReleaseEvent` and restore it in `__init__`.

## How to Verify
1.  **Run** the app (`start_app.bat`).
2.  **Drag** the green ball to a specific spot.
3.  **Close** the app (Right-click ball -> Exit).
4.  **Restart** the app. The ball should appear exactly where you left it.
5.  **Expand** the list. It should be a fixed size. If you have many files, a vertical scrollbar will appear.
6.  **Right-click** a file in the list. Nothing should happen.
