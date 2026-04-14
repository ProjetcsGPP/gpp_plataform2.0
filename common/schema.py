from drf_spectacular.utils import extend_schema_view, extend_schema

def tag_all_actions(tag: str):
    """Aplica a mesma tag a todas as actions padrão de um ViewSet."""
    actions = ["list", "retrieve", "create", "update", "partial_update", "destroy"]
    return extend_schema_view(**{action: extend_schema(tags=[tag]) for action in actions})