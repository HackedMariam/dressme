import React from 'react';

/** A crash in one page shows a message there instead of blanking the whole app */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prev) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="banner banner-bad" role="alert">
        Cette page a rencontré une erreur ({String(this.state.error.message || this.state.error)}).
        <button className="link" onClick={() => this.setState({ error: null })}>Réessayer</button>
      </div>
    );
  }
}
