from pydantic import BaseModel
from typing import Optional

class UserRegister(BaseModel):

    full_name: Optional[str] = ""
    mobile: Optional[str] = ""
    email: Optional[str] = ""
    password: Optional[str] = ""

    state: Optional[str] = ""
    district: Optional[str] = ""
    village: Optional[str] = ""

    farm_type: Optional[str] = ""


class UserLogin(BaseModel):

    email: str
    password: str