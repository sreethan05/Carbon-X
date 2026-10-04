import { useState } from "react";

import axios from "axios";

import { useNavigate } from "react-router-dom";

export default function Register() {

  const navigate = useNavigate();

  const [formData, setFormData] =
    useState({

      full_name: "",
      mobile: "",
      email: "",
      password: "",
      country: "",
      state: "",
      city: "",
      farm_type: ""

    });

  const handleChange = (e) => {

    setFormData({

      ...formData,

      [e.target.name]:
        e.target.value

    });

  };

  const register = async () => {

    try {

      const response =
        await axios.post(
          "http://127.0.0.1:5000/register",
          formData
        );

      if (
        response.data.success
      ) {

        alert(
          "OTP sent to email"
        );

        navigate(
          "/verify-email"
        );

      } else {

        alert(
          response.data.message
        );

      }

    } catch (err) {

      alert(
        "Registration failed"
      );

    }

  };

  return (

    <div
      style={styles.container}
    >

      <div
        style={styles.card}
      >

        <h1
          style={styles.title}
        >
          Register
        </h1>

        <input
          name="full_name"
          placeholder="Full Name"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="mobile"
          placeholder="Mobile Number"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="email"
          placeholder="Email Address"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          type="password"
          name="password"
          placeholder="Password"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="country"
          placeholder="Country"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="state"
          placeholder="State"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="city"
          placeholder="City / District"
          onChange={handleChange}
          style={styles.input}
        />

        <input
          name="farm_type"
          placeholder="Crop Type"
          onChange={handleChange}
          style={styles.input}
        />

        <button
          onClick={register}
          style={styles.button}
        >
          Register
        </button>

      </div>

    </div>

  );

}

const styles = {

  container: {

    width: "100vw",

    minHeight: "100vh",

    display: "flex",

    justifyContent: "center",

    alignItems: "center",

    background:
      "#f2f5f9"

  },

  card: {

    width: 420,

    background: "white",

    padding: 40,

    borderRadius: 20,

    boxShadow:
      "0 5px 20px rgba(0,0,0,0.15)",

    display: "flex",

    flexDirection: "column"

  },

  title: {

    textAlign: "center",

    marginBottom: 30,

    color: "#1d3557"

  },

  input: {

    padding: 16,

    marginBottom: 18,

    borderRadius: 12,

    border:
      "1px solid #d0d7de",

    fontSize: 16,

    outline: "none"

  },

  button: {

    padding: 16,

    background: "#27ae60",

    color: "white",

    border: "none",

    borderRadius: 12,

    fontSize: 18,

    fontWeight: "bold",

    cursor: "pointer",

    marginTop: 10

  }

};