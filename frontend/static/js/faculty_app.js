// Faculty Control Interface - React Component
const { useState, useEffect } = React;

function FacultyApp() {
  const [token, setToken] = useState(
    localStorage.getItem("faculty_token") || "faculty_super_secret_token_bt2404"
  );
  const [settings, setSettings] = useState({
    faculty_test_mode: false,
    show_pulp_code: false,
    show_validation_diagnostics: false,
    show_debug_parsed_model: false,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);
  const [showConfirmModal, setShowConfirmModal] = useState(false);

  const fetchSettings = async (authToken) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const res = await fetch("/api/faculty/settings", {
        headers: {
          "X-Faculty-Token": authToken || token,
        },
      });
      if (res.status === 401) {
        setErrorMsg("Unauthorized: Invalid faculty authentication token.");
      } else if (!res.ok) {
        setErrorMsg("Failed to load settings from server.");
      } else {
        const data = await res.json();
        setSettings(data);
      }
    } catch (err) {
      setErrorMsg("Network error connecting to backend API.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings(token);
  }, []);

  const handleTokenSave = (e) => {
    e.preventDefault();
    localStorage.setItem("faculty_token", token);
    setStatusMsg("Faculty token updated.");
    setTimeout(() => setStatusMsg(null), 3000);
    fetchSettings(token);
  };

  const handleToggle = async (key) => {
    const newSettings = { ...settings, [key]: !settings[key] };
    try {
      const res = await fetch("/api/faculty/settings", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Faculty-Token": token,
        },
        body: JSON.stringify({ [key]: newSettings[key] }),
      });
      if (!res.ok) {
        setErrorMsg("Failed to update setting. Ensure faculty token is valid.");
      } else {
        const data = await res.json();
        setSettings(data);
        setStatusMsg("Setting updated successfully.");
        setTimeout(() => setStatusMsg(null), 2000);
      }
    } catch (err) {
      setErrorMsg("Error communicating with server.");
    }
  };

  const handleEnableExamSafeMode = async () => {
    try {
      const res = await fetch("/api/faculty/exam-safe-mode", {
        method: "POST",
        headers: {
          "X-Faculty-Token": token,
        },
      });
      if (!res.ok) {
        setErrorMsg("Failed to enforce Exam Safe Mode.");
      } else {
        const data = await res.json();
        setSettings(data);
        setShowConfirmModal(false);
        setStatusMsg("Exam Safe Mode activated successfully.");
        setTimeout(() => setStatusMsg(null), 4000);
      }
    } catch (err) {
      setErrorMsg("Error communicating with server.");
    }
  };

  const isExamSafe =
    !settings.faculty_test_mode &&
    !settings.show_pulp_code &&
    !settings.show_validation_diagnostics &&
    !settings.show_debug_parsed_model;

  return React.createElement(
    "div",
    { className: "container" },

    // Header
    React.createElement(
      "div",
      { className: "header-section" },
      React.createElement(
        "div",
        { className: "header-logo-container" },
        React.createElement("img", {
          src: "/static/images/ntu_nbs_logo.png",
          alt: "Nanyang Technological University Singapore | Nanyang Business School",
          className: "university-logo",
        })
      ),
      React.createElement(
        "h1",
        { className: "main-title" },
        "Optimization Solver — Faculty Controls",
        React.createElement(
          "span",
          { className: `faculty-badge ${isExamSafe ? "safe" : "test"}` },
          isExamSafe ? "EXAM SAFE MODE" : "FACULTY TEST MODE"
        )
      ),
      React.createElement(
        "p",
        { className: "subtitle", style: { fontSize: "1rem", color: "var(--text-muted)" } },
        "Server-enforced administrative controls for examination integrity."
      )
    ),

    // Notifications
    statusMsg &&
      React.createElement("div", { className: "alert-box alert-success" }, statusMsg),
    errorMsg &&
      React.createElement("div", { className: "alert-box alert-danger" }, errorMsg),

    // Current State Alert
    isExamSafe
      ? React.createElement(
          "div",
          { className: "alert-box alert-success" },
          "Exam Safe Mode is active. Faculty testing, diagnostic information, debug information and student PuLP-code display are disabled."
        )
      : React.createElement(
          "div",
          { className: "alert-box alert-warning" },
          "⚠️ Faculty Test Mode is active. Some testing or diagnostic features may be visible on the examination interface."
        ),

    // Faculty Authentication Card
    React.createElement(
      "div",
      { className: "instructions-card", style: { marginBottom: "2rem" } },
      React.createElement(
        "form",
        { onSubmit: handleTokenSave },
        React.createElement(
          "label",
          { className: "input-label", style: { fontSize: "0.9rem" } },
          "Faculty Secret Token (Server Authorization Header)"
        ),
        React.createElement(
          "div",
          { style: { display: "flex", gap: "0.5rem" } },
          React.createElement("input", {
            type: "password",
            value: token,
            onChange: (e) => setToken(e.target.value),
            style: {
              flex: 1,
              padding: "0.5rem 0.75rem",
              border: "1px solid var(--border-color)",
              borderRadius: "4px",
              fontFamily: "var(--font-mono)",
            },
            placeholder: "Enter faculty token",
          }),
          React.createElement(
            "button",
            { type: "submit", className: "btn btn-secondary", style: { padding: "0.5rem 1rem" } },
            "Save & Reconnect"
          )
        )
      )
    ),

    // Application Controls
    React.createElement("h2", { className: "section-title" }, "Application Controls"),
    React.createElement(
      "div",
      { className: "instructions-card", style: { padding: "0.5rem 1.5rem" } },

      // Control 1: Faculty Test Mode
      React.createElement(
        "div",
        { className: "control-item" },
        React.createElement(
          "div",
          null,
          React.createElement("div", { className: "control-info-title" }, "Faculty Test Mode"),
          React.createElement(
            "div",
            { className: "control-info-desc" },
            "Displays pre-configured test formulation buttons on the student interface."
          )
        ),
        React.createElement(
          "label",
          { className: "switch" },
          React.createElement("input", {
            type: "checkbox",
            checked: settings.faculty_test_mode,
            onChange: () => handleToggle("faculty_test_mode"),
            disabled: isLoading,
          }),
          React.createElement("span", { className: "slider" })
        )
      ),

      // Control 2: Show PuLP Code
      React.createElement(
        "div",
        { className: "control-item" },
        React.createElement(
          "div",
          null,
          React.createElement("div", { className: "control-info-title" }, "Show PuLP Code"),
          React.createElement(
            "div",
            { className: "control-info-desc" },
            "Includes generated Python PuLP code in solver results."
          )
        ),
        React.createElement(
          "label",
          { className: "switch" },
          React.createElement("input", {
            type: "checkbox",
            checked: settings.show_pulp_code,
            onChange: () => handleToggle("show_pulp_code"),
            disabled: isLoading,
          }),
          React.createElement("span", { className: "slider" })
        )
      ),

      // Control 3: Show Validation Diagnostics
      React.createElement(
        "div",
        { className: "control-item" },
        React.createElement(
          "div",
          null,
          React.createElement(
            "div",
            { className: "control-info-title" },
            "Show Validation Diagnostics"
          ),
          React.createElement(
            "div",
            { className: "control-info-desc" },
            "Includes detailed multi-gate validation pipeline diagnostics for authorized faculty."
          )
        ),
        React.createElement(
          "label",
          { className: "switch" },
          React.createElement("input", {
            type: "checkbox",
            checked: settings.show_validation_diagnostics,
            onChange: () => handleToggle("show_validation_diagnostics"),
            disabled: isLoading,
          }),
          React.createElement("span", { className: "slider" })
        )
      ),

      // Control 4: Show Debug Parsed Model
      React.createElement(
        "div",
        { className: "control-item", style: { borderBottom: "none" } },
        React.createElement(
          "div",
          null,
          React.createElement("div", { className: "control-info-title" }, "Show Debug Parsed Model"),
          React.createElement(
            "div",
            { className: "control-info-desc" },
            "Displays internal JSON structured mathematical model representation."
          )
        ),
        React.createElement(
          "label",
          { className: "switch" },
          React.createElement("input", {
            type: "checkbox",
            checked: settings.show_debug_parsed_model,
            onChange: () => handleToggle("show_debug_parsed_model"),
            disabled: isLoading,
          }),
          React.createElement("span", { className: "slider" })
        )
      )
    ),

    // Enable Exam Safe Mode Action
    React.createElement(
      "div",
      { style: { marginTop: "2rem" } },
      React.createElement(
        "button",
        {
          type: "button",
          className: "btn btn-primary",
          style: { backgroundColor: "#1e3a8a" },
          onClick: () => setShowConfirmModal(true),
          disabled: isExamSafe,
        },
        "Enable Exam Safe Mode"
      )
    ),

    // Confirmation Modal for Exam Safe Mode
    showConfirmModal &&
      React.createElement(
        "div",
        { className: "modal-overlay" },
        React.createElement(
          "div",
          { className: "modal-card" },
          React.createElement("h3", { className: "modal-title" }, "Enforce Exam Safe Mode?"),
          React.createElement(
            "p",
            { className: "modal-body" },
            "This will immediately disable Faculty Test Mode, PuLP Code display, Validation Diagnostics, and Debug Model across all active sessions. Students will not be able to view any administrative or diagnostic details."
          ),
          React.createElement(
            "div",
            { className: "modal-actions" },
            React.createElement(
              "button",
              {
                type: "button",
                className: "btn btn-secondary",
                onClick: () => setShowConfirmModal(false),
              },
              "Cancel"
            ),
            React.createElement(
              "button",
              {
                type: "button",
                className: "btn btn-primary",
                style: { backgroundColor: "#1e3a8a" },
                onClick: handleEnableExamSafeMode,
              },
              "Confirm & Enable"
            )
          )
        )
      )
  );
}

// Render Faculty Interface
ReactDOM.render(
  React.createElement(FacultyApp),
  document.getElementById("faculty-root")
);
