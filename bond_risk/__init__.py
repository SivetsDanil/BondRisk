def create_app(test_config=None):
    # Keep the entry point used by `flask --app bond_risk`.
    from main import create_app as create_web_app

    return create_web_app(test_config)
