import React from 'react';
import ReactDOM from 'react-dom';

export default class SearchBox extends React.Component {
  static defaultProps = { placeholder: 'Search products' };

  componentDidMount() {
    this.refs.query.focus();
    const node = ReactDOM.findDOMNode(this);
    node.classList.add('search-box--ready');
  }

  submit = (event) => {
    event.preventDefault();
    this.props.onSearch(this.refs.query.value);
  };

  render() {
    return (
      <form onSubmit={this.submit}>
        <input ref="query" placeholder={this.props.placeholder} />
        <button type="submit">Go</button>
      </form>
    );
  }
}
