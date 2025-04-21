"""API endpoint modules for the bitHuman Visual Agent.

This package contains the API endpoints organized by functional area.
Each module in this package is responsible for a specific set of related API endpoints.
"""

# List of modules that should be imported and registered
endpoint_modules = [
    "model_endpoints",
    "asset_endpoints",
    "status_endpoints",
]


def register_all_endpoints(app, model_loader):
    """Register all API endpoints with the Flask application.

    Args:
        app: The Flask application
        model_loader: The model loader instance
    """
    # Import and register each endpoint module
    from . import asset_endpoints, model_endpoints, status_endpoints

    # Register endpoints from each module
    model_endpoints.register_endpoints(app, model_loader)
    asset_endpoints.register_endpoints(app, model_loader)
    status_endpoints.register_endpoints(app, model_loader)
