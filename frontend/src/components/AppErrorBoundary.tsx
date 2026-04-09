import { Component, type ErrorInfo, type ReactNode } from "react";

import { signOut } from "../app/auth";
import { navigate } from "../app/router";

interface AppErrorBoundaryProps {
  children: ReactNode;
}

interface AppErrorBoundaryState {
  hasError: boolean;
  errorMessage: string | null;
}

export class AppErrorBoundary extends Component<
  AppErrorBoundaryProps,
  AppErrorBoundaryState
> {
  state: AppErrorBoundaryState = {
    hasError: false,
    errorMessage: null,
  };

  static getDerivedStateFromError(error: Error): AppErrorBoundaryState {
    return {
      hasError: true,
      errorMessage: error.message || "Unexpected application error.",
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Application render failed.", error, errorInfo);
  }

  handleReset = () => {
    signOut();
    this.setState({
      hasError: false,
      errorMessage: null,
    });
    navigate("/login");
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="login-shell">
          <section className="login-hero">
            <div className="login-copy">
              <p className="eyebrow">Application Recovery</p>
              <h1>We hit a page error after sign-in</h1>
              <p className="summary">
                The application caught a runtime error instead of leaving you on a blank
                screen. Use the recovery action below to return to the login page and start
                a clean session.
              </p>
            </div>

            <div className="login-card panel">
              <div className="section-heading">
                <h2>Recovery Details</h2>
                <p>
                  {this.state.errorMessage ??
                    "Unexpected application error. Please sign in again."}
                </p>
              </div>

              <button className="primary-button login-submit" onClick={this.handleReset} type="button">
                Return To Login
              </button>
            </div>
          </section>
        </div>
      );
    }

    return this.props.children;
  }
}
