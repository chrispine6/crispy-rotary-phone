from fastapi import Depends, HTTPException, status, Request

# This middleware expects request.state.user to be set by your Firebase authentication logic.
# Make sure your authentication dependency sets request.state.user with an 'admin' field.

async def admin_check(request: Request):
    # Disable admin check for development/testing
    return True
    # user = getattr(request.state, "user", None)
    # if not user or not getattr(user, "admin", False):
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Admin privileges required"
    #     )
    # return user
    # return user
