from pydantic import BaseModel, ConfigDict, Field


class AuthSchema(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class LoginRequest(AuthSchema):
    rep_id: int = Field(alias="repId", gt=0)


class CurrentUserDTO(AuthSchema):
    rep_id: int = Field(alias="repId")
    username: str
    role: str
    region_id: int | None = Field(alias="regionId")


class LoginResponse(AuthSchema):
    access_token: str = Field(alias="accessToken")
    token_type: str = Field(default="bearer", alias="tokenType")
    user: CurrentUserDTO
