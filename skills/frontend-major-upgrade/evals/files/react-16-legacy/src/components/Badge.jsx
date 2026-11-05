import React from 'react';
import PropTypes from 'prop-types';

export default function Badge({ label, tone }) {
  return <span className={'badge badge--' + tone}>{label}</span>;
}

Badge.propTypes = { label: PropTypes.string.isRequired, tone: PropTypes.string };

Badge.defaultProps = { tone: 'info' };
