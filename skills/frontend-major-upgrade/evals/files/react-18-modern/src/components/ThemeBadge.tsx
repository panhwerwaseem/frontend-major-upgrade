import { Component } from 'react';

import { ThemeContext } from '../theme';

type Props = { label: string; tone: string };

export default class ThemeBadge extends Component<Props> {
  static contextType = ThemeContext;
  static defaultProps = { tone: 'info' };
  declare context: string;

  render() {
    // contextTypes and getChildContext were removed from this file in 2022.
    return (
      <span className={'badge badge--' + this.props.tone} style={{ color: this.context }}>
        {this.props.label}
      </span>
    );
  }
}
