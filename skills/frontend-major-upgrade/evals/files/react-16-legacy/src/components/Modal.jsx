import React from 'react';
import ReactDOM from 'react-dom';
import { LocaleContext } from '../locale';

export default class Modal extends React.Component {
  static contextType = LocaleContext;

  componentDidMount() {
    this.host = document.createElement('div');
    document.body.appendChild(this.host);
    ReactDOM.render(<div className="modal">{this.props.children}</div>, this.host);
  }

  componentWillUnmount() {
    ReactDOM.unmountComponentAtNode(this.host);
    document.body.removeChild(this.host);
  }

  render() {
    return null;
  }
}
