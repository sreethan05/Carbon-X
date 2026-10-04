import { useState } from "react";

import axios from "axios";

import { useNavigate } from "react-router-dom";

export default function VerifyEmail() {

  const navigate = useNavigate();

  const [email, setEmail] =
    useState("");

  const [otp, setOtp] =
    useState("");

  const verify = async () => {

    try {

      const response =
        await axios.post(
          "http://127.0.0.1:5000/verify-email",
          {
            email,
            otp
          }
        );

      if (
        response.data.success
      ) {

        alert(
          "Email verified"
        );

        navigate("/");

      } else {

        alert(
          response.data.message
        );

      }

    } catch {

      alert(
        "Verification failed"
      );

    }

  };

  return (

    <div>

      <h1>Email Verification</h1>

      <input
        placeholder="Email"
        onChange={(e) =>
          setEmail(
            e.target.value
          )
        }
      />

      <input
        placeholder="OTP"
        onChange={(e) =>
          setOtp(
            e.target.value
          )
        }
      />

      <button onClick={verify}>
        Verify
      </button>

    </div>

  );

}