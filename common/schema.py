from drf_spectacular.utils import extend_schema, extend_schema_view


def tag_all_actions(tag: str):
    """
    Decorator que aplica uma tag OpenAPI a todas as actions existentes no ViewSet.
    Ignora silenciosamente actions que o ViewSet não implementa (ex: ReadOnly).
    """
    ALL_ACTIONS = ["list", "retrieve", "create", "update", "partial_update", "destroy"]

    def decorator(cls):
        available = {
            action: extend_schema(tags=[tag])
            for action in ALL_ACTIONS
            if callable(getattr(cls, action, None))
        }
        if available:
            cls = extend_schema_view(**available)(cls)
        return cls

    return decorator
