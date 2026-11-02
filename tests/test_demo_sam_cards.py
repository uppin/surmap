"""Demo: each SAM object's id sits on its own card, joined to the object, never overlapping."""

import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from surmap.demo.view_math import VIEW_HELPERS
from tests.test_demo_object_feed import a_console_page, needs_node
from tests.test_demo_sam_pick import SAM_PAGE, run_js

WIDTH, HEIGHT = 620, 188  # the KITTI display size

# Five cards, 90 x 30 px, for small far objects (12 x 8 px boxes) bunched around (300, 120).
BUNCHED = json.dumps(
    [
        {
            "key": k,
            "anchor": [300 + 14 * k, 120],
            "box": [294 + 14 * k, 116, 306 + 14 * k, 124],
            "width": 90,
            "height": 30,
        }
        for k in range(5)
    ]
)


def gap(card: "Card", box: tuple[float, float, float, float]) -> float:
    """How far a card is from a mask box (0 when they touch or overlap)."""
    dx = max(box[0] - (card.x + card.width), card.x - box[2], 0.0)
    dy = max(box[1] - (card.y + card.height), card.y - box[3], 0.0)
    return float((dx * dx + dy * dy) ** 0.5)


def covers(card: "Card", box: tuple[float, float, float, float]) -> bool:
    return (
        card.x < box[2]
        and box[0] < card.x + card.width
        and card.y < box[3]
        and box[1] < card.y + card.height
    )


@dataclass(frozen=True)
class Card:
    """A laid-out card, and its leader from the card to its object."""

    key: int
    x: float
    y: float
    width: float
    height: float
    start: tuple[float, float]
    end: tuple[float, float]

    def nearest_edge_point(self, point: tuple[float, float]) -> tuple[float, float]:
        """The point of this card nearest `point` (on its edge when `point` is outside)."""
        x, y = point
        return (min(max(x, self.x), self.x + self.width), min(max(y, self.y), self.y + self.height))


def overlap(a: Card, b: Card) -> bool:
    return (
        a.x < b.x + b.width
        and b.x < a.x + a.width
        and a.y < b.y + b.height
        and b.y < a.y + a.height
    )


def laid_out(items: str) -> list[Card]:
    raw = cast(
        "list[dict[str, Any]]",
        run_js(VIEW_HELPERS.format(), f"layoutCards({items}, {WIDTH}, {HEIGHT})"),
    )
    return [
        Card(
            int(c["key"]),
            float(c["x"]),
            float(c["y"]),
            float(c["width"]),
            float(c["height"]),
            (float(c["from"][0]), float(c["from"][1])),
            (float(c["to"][0]), float(c["to"][1])),
        )
        for c in raw
    ]


def on_image(card: Card) -> bool:
    return (
        0 <= card.x
        and card.x + card.width <= WIDTH
        and 0 <= card.y
        and card.y + card.height <= HEIGHT
    )


@needs_node
def test_cards_for_bunched_objects_never_overlap() -> None:
    # When five bunched objects' cards are laid out
    cards = laid_out(BUNCHED)

    # Then all five are placed, and no two overlap
    assert [card.key for card in cards] == [0, 1, 2, 3, 4]
    assert [(a.key, b.key) for a, b in itertools.combinations(cards, 2) if overlap(a, b)] == []


@needs_node
def test_cards_stay_on_the_image() -> None:
    # Given objects at both top corners and the bottom corner
    edges = json.dumps(
        [
            {"key": 1, "anchor": [2, 5], "width": 90, "height": 30},
            {"key": 2, "anchor": [618, 5], "width": 90, "height": 30},
            {"key": 3, "anchor": [618, 186], "width": 90, "height": 30},
        ]
    )

    # When their cards are laid out
    cards = laid_out(edges)

    # Then none runs off the image
    assert [card.key for card in cards if not on_image(card)] == []


@needs_node
def test_a_card_with_room_sits_right_above_its_object() -> None:
    # Given one car whose mask box spans (250, 100)-(350, 170)
    item = {"key": 7, "anchor": [300, 135], "box": [250, 100, 350, 170], "width": 90, "height": 30}

    # When its card is laid out
    (card,) = laid_out(json.dumps([item]))

    # Then it sits centred just above the box, touching distance away, not over the car
    assert card.key == 7
    assert card.x + card.width / 2 == 300
    assert gap(card, (250, 100, 350, 170)) <= 4
    assert not covers(card, (250, 100, 350, 170))


@needs_node
def test_with_no_room_above_a_card_goes_beside_or_below_its_object_not_far_off() -> None:
    # Given a car at the top edge of the image
    item = {"key": 1, "anchor": [300, 20], "box": [260, 2, 340, 40], "width": 90, "height": 30}

    # When its card is laid out
    (card,) = laid_out(json.dumps([item]))

    # Then it is not above the car, still touches its box, and does not cover it
    assert card.y >= 2
    assert gap(card, (260, 2, 340, 40)) <= 4
    assert not covers(card, (260, 2, 340, 40))


@needs_node
def test_bunched_objects_cards_stay_near_their_own_objects() -> None:
    # When five small far cars' cards are laid out side by side
    cards = laid_out(BUNCHED)

    # Then every card is placed near its own car, the nearest ones touching distance away
    gaps = sorted(gap(card, (294 + 14 * card.key, 116, 306 + 14 * card.key, 124)) for card in cards)
    assert gaps[0] <= 4
    assert [g for g in gaps if g > 80] == []


@needs_node
def test_each_card_leads_to_its_object_from_its_nearest_edge() -> None:
    # When five bunched objects' cards are laid out
    cards = laid_out(BUNCHED)

    # Then each leader ends on its object's anchor and starts at the card's edge point
    # nearest that anchor
    anchors = [(300.0 + 14 * card.key, 120.0) for card in cards]
    assert [card.end for card in cards] == anchors
    assert [card.start for card in cards] == [
        pytest.approx(card.nearest_edge_point(anchor))
        for card, anchor in zip(cards, anchors, strict=True)
    ]


@needs_node
def test_the_card_under_the_cursor_is_found() -> None:
    picks = run_js(
        VIEW_HELPERS.format(),
        "(() => { const cards = [{key: 3, x: 10, y: 10, width: 50, height: 20},"
        " {key: 4, x: 80, y: 10, width: 50, height: 20}];"
        " return [cardAt(cards, 20, 15), cardAt(cards, 100, 25), cardAt(cards, 70, 15)]; })()",
    )
    assert picks == [3, 4, 0]


# The stub SAM page from test_demo_sam_pick: frame 13 shows car track 8 (surface 27)
# and track 5 (no surface yet), both labelled "car" as SAM labels its objects.
# Text is measured as 6 px a character.
CAR_PAGE = SAM_PAGE + "\nsamLast.data.objects.forEach((object) => { object.label = 'car'; });"
CARDS = "samCardsFor(samLast.data, (text) => text.length * 6)"


@needs_node
def test_a_linked_objects_card_names_its_surface_and_depth_range() -> None:
    # Given track 8's dense points span 6.1 to 7.3 m
    prelude = (
        CAR_PAGE
        + "\nnoteRegions({frame_id: 13,"
        + " regions: [{track_id: 8, pixels: [[5, 5, 6.1], [6, 6, 7.3]]}]});"
    )
    cards = run_js(
        prelude, f"{CARDS}.map((card) => [card.key, card.lines, card.surface, card.pending])"
    )
    # Then track 8's card names car #27 and its range; track 5, with no points yet, is
    # named by its track and marked pending (drawn in the pending colour, no "SAM" tag)
    assert cards == [
        [8, ["car #27", "6.1–7.3 m"], 27, False],
        [5, ["car #5"], 0, True],
    ]


@needs_node
def test_hovering_a_card_selects_its_object() -> None:
    picked = run_js(
        CAR_PAGE,
        f"(() => {{ samCardRects = {CARDS}; const card = samCardRects[0];"
        " return samSurfaceAt(card.x + 2, card.y + 2); })()",
    )
    assert picked == 27


def test_the_sam_view_draws_cards_not_loose_labels(tmp_path: Path) -> None:
    with a_console_page(tmp_path) as page:
        script = page.split("<script>", 1)[1]
    objects = script.split("function drawSamObjects(", 1)[1].split("\n}", 1)[0]
    redraw = script.split("function redrawSam()", 1)[1].split("\n}", 1)[0]
    assert "fillText" not in objects
    assert "drawSamCards(" in redraw


def test_cards_of_objects_without_points_are_colour_coded_and_explained(tmp_path: Path) -> None:
    with a_console_page(tmp_path) as page:
        script = page.split("<script>", 1)[1]
    cards = script.split("function drawSamCards(", 1)[1].split("\n}", 1)[0]
    # A pending card has its own colour, and the SAM view's legend says what each means
    assert "card.pending" in cards and "SAM_PENDING_COLOUR" in cards
    assert "SAM " not in cards
    assert 'id="sam-card-legend"' in page
