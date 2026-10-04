from fastapi import APIRouter
from app.models import (
    UserRegister,
    UserLogin
)

from app.database import users_collection

router = APIRouter()


@router.post("/register")

def register(user: UserRegister):

    existing_user = users_collection.find_one({

        "email": user.email

    })

    if existing_user:

        return {

            "detail":
            "Email already registered"

        }

    user_data = {

        "full_name":
        user.full_name,

        "mobile":
        user.mobile,

        "email":
        user.email,

        "password":
        user.password,

        "state":
        user.state,

        "district":
        user.district,

        "village":
        user.village,

        "farm_type":
        user.farm_type

    }

    users_collection.insert_one(
        user_data
    )

    return {

        "message":
        "Registration successful"

    }


@router.post("/login")

def login(user: UserLogin):

    existing_user = users_collection.find_one({

        "email": user.email

    })

    if not existing_user:

        return {

            "detail":
            "Invalid email"

        }

    if (
        user.password !=
        existing_user["password"]
    ):

        return {

            "detail":
            "Invalid password"

        }

    return {

        "message":
        "Login successful",

        "user": {

            "full_name":
            existing_user["full_name"],

            "email":
            existing_user["email"]

        }

    }