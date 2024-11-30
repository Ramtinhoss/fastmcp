"""Resource template functionality."""

import inspect
import re
from typing import Any, Callable, Dict, Optional

from pydantic import BaseModel, Field, TypeAdapter, validate_call

from fastmcp.resources.types import FunctionResource, Resource


class ResourceTemplate(BaseModel):
    """A template for dynamically creating resources."""

    uri_template: str = Field(
        description="URI template with parameters (e.g. weather://{city}/current)"
    )
    name: str = Field(description="Name of the resource")
    description: str | None = Field(description="Description of what the resource does")
    mime_type: str = Field(
        default="text/plain", description="MIME type of the resource content"
    )
    func: Callable = Field(exclude=True)
    parameters: dict = Field(description="JSON schema for function parameters")

    @classmethod
    def from_function(
        cls,
        func: Callable,
        uri_template: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> "ResourceTemplate":
        """Create a template from a function."""
        func_name = name or func.__name__
        if func_name == "<lambda>":
            raise ValueError("You must provide a name for lambda functions")

        # Get schema from TypeAdapter - will fail if function isn't properly typed
        parameters = TypeAdapter(func).json_schema()

        # ensure the arguments are properly cast
        func = validate_call(func)

        return cls(
            uri_template=uri_template,
            name=func_name,
            description=description or func.__doc__ or "",
            mime_type=mime_type or "text/plain",
            func=func,
            parameters=parameters,
        )

    def matches(self, uri: str) -> Optional[Dict[str, Any]]:
        """Check if URI matches template and extract parameters."""
        # Convert template to regex pattern
        pattern = self.uri_template.replace("{", "(?P<").replace("}", ">[^/]+)")
        match = re.match(f"^{pattern}$", uri)
        if match:
            return match.groupdict()
        return None

    async def create_resource(self, uri: str, params: Dict[str, Any]) -> Resource:
        """Create a resource from the template with the given parameters."""
        try:
            # Call function and check if result is a coroutine
            result = self.func(**params)
            if inspect.iscoroutine(result):
                result = await result

            return FunctionResource(
                uri=uri,
                name=self.name,
                description=self.description,
                mime_type=self.mime_type,
                func=lambda: result,  # Capture result in closure
            )
        except Exception as e:
            raise ValueError(f"Error creating resource from template: {e}")
