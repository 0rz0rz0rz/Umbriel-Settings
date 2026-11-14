"""Umbriel keybind action catalog (from umbriel_core) plus the Qt dropdown model."""

from umbriel_core.actions import (  # noqa: F401  re-exported for the GUI modules
    ACTION_CATEGORIES,
    ACTION_DOCS,
    ACTION_INFO,
    ACTION_TEMPLATES,
    ARG_HELP,
    REQUIRED_ARG_ACTIONS,
    migrate_action,
    parse_actions,
    reduce_template,
)

from .common import (
    QStandardItem,
    QStandardItemModel,
    Qt,
)


def build_action_model():
    """Build the dropdown model: a disabled header per category, then every action with its description as tooltip."""
    m = QStandardItemModel()
    for cat, items in ACTION_CATEGORIES:
        h = QStandardItem(f"-- {cat} --")
        h.setFlags(Qt.ItemFlag.NoItemFlags)
        m.appendRow(h)
        for a, d in items:
            it = QStandardItem(a)
            it.setToolTip(d)
            m.appendRow(it)
    return m



# ------------------------------------------------------------------ field model
