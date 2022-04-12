from typing import Optional

from gaphas.connector import Handle
from gaphas.guide import GuidedItemHandleMoveMixin
from gaphas.handlemove import ConnectionSinkType, HandleMove, ItemHandleMove
from gaphas.item import Item, Line
from gaphas.types import Pos
from gaphas.view import GtkView

from gaphor.diagram.connectors import Connector


def connectable(line, handle, element):
    connector = Connector(element, line)
    for port in element.ports():
        allow = connector.allow(handle, port)
        if allow:
            return True
    return False


class GrayOutLineHandleMoveMixin:

    view: GtkView
    item: Item
    handle: Handle

    def start_move(self, pos):
        super().start_move(pos)  # type: ignore[misc]
        handle = self.handle
        if handle.connectable:
            line = self.item
            model = self.view.model
            selection = self.view.selection
            selection.grayed_out_items = {
                item
                for item in model.get_all_items()
                if not (item is line or connectable(line, handle, item))
            }

    def stop_move(self, pos):
        super().stop_move(pos)  # type: ignore[misc]
        selection = self.view.selection
        selection.grayed_out_items = set()
        selection.dropzone_item = None

    def glue(
        self, pos: Pos, distance: int = ItemHandleMove.GLUE_DISTANCE
    ) -> Optional[ConnectionSinkType]:
        sink = super().glue(pos, distance)  # type: ignore[misc]
        self.view.selection.dropzone_item = sink and sink.item
        return sink

    def connect(self, pos: Pos) -> None:
        super().connect(pos)  # type: ignore[misc]
        self.view.selection.dropzone_item = None


@HandleMove.register(Line)
class GrayOutLineHandleMove(
    GrayOutLineHandleMoveMixin, GuidedItemHandleMoveMixin, ItemHandleMove
):
    pass
