import React from 'react';
import PropTypes from 'prop-types';

export default class ThemeProvider extends React.Component {
  static childContextTypes = { color: PropTypes.string };

  getChildContext() {
    return { color: this.props.color };
  }

  render() {
    return <div className="theme">{this.props.children}</div>;
  }
}

export function ThemedLabel(props, context) {
  return <span style={{ color: context.color }}>{props.children}</span>;
}

ThemedLabel.contextTypes = { color: PropTypes.string };
