import { useState } from "react";
import axios from "axios";
import { useNavigate, Link } from "react-router-dom";

export default function Login() {

  const navigate = useNavigate();

  const [email, setEmail] =
    useState("");

  const [password, setPassword] =
    useState("");

  const [showPassword, setShowPassword] =
    useState(false);

  const login = async () => {

    if (!email || !password) {

      alert(
        "Please enter email and password"
      );

      return;

    }

    try {

      const response =
        await axios.post(
          "http://127.0.0.1:5000/login",
          {
            email,
            password
          }
        );

      if (response.data.success) {

        localStorage.setItem(
          "token",
          response.data.token
        );

        localStorage.setItem(
          "user",
          JSON.stringify(
            response.data.user
          )
        );

        navigate("/dashboard");

      } else {

        alert(
          response.data.message
        );

      }

    } catch (err) {

      console.log(err);

      alert(
        "Invalid login credentials"
      );

    }

  };

  return (

    <div
      style={{
        width: "100vw",
        height: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "#f2f2f2"
      }}
    >

      <div
        style={{
          width: 400,
          background: "white",
          padding: 40,
          borderRadius: 20
        }}
      >

        <h1>Login</h1>

        <input
          placeholder="Email"
          value={email}
          onChange={(e) =>
            setEmail(
              e.target.value
            )
          }
          style={inputStyle}
        />

        <div
          style={{
            position: "relative"
          }}
        >

          <input
            type={
              showPassword
                ? "text"
                : "password"
            }
            placeholder="Password"
            value={password}
            onChange={(e) =>
              setPassword(
                e.target.value
              )
            }
            style={inputStyle}
          />

          <span
            onClick={() =>
              setShowPassword(
                !showPassword
              )
            }
            style={{
              position: "absolute",
              right: 20,
              top: 22,
              cursor: "pointer"
            }}
          >
            {
              showPassword
                ? "Hide"
                : "Show"
            }
          </span>

        </div>

        <button
          onClick={login}
          style={buttonStyle}
        >
          Login
        </button>

        <p>

          Don't have account?

          <Link to="/register">
            Register
          </Link>

        </p>

      </div>

    </div>

  );

}

const inputStyle = {
  width: "100%",
  padding: 16,
  marginTop: 20,
  borderRadius: 12,
  border: "1px solid #ccc",
  fontSize: 16,
  boxSizing: "border-box"
};

const buttonStyle = {
  width: "100%",
  padding: 16,
  marginTop: 24,
  background: "#27ae60",
  color: "white",
  border: "none",
  borderRadius: 12,
  fontSize: 18,
  cursor: "pointer"
};