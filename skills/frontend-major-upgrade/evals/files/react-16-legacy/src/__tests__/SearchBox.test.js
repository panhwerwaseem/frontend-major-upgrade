import React from 'react';
import TestUtils from 'react-dom/test-utils';
import ShallowRenderer from 'react-test-renderer/shallow';
import SearchBox from '../components/SearchBox';

test('renders a form', () => {
  const renderer = new ShallowRenderer();
  renderer.render(<SearchBox onSearch={() => {}} />);
  expect(renderer.getRenderOutput().type).toBe('form');
});

test('submits the typed text', () => {
  const onSearch = jest.fn();
  const box = TestUtils.renderIntoDocument(<SearchBox onSearch={onSearch} />);
  box.refs.query.value = 'kettle';
  TestUtils.Simulate.submit(TestUtils.findRenderedDOMComponentWithTag(box, 'form'));
  expect(onSearch).toHaveBeenCalledWith('kettle');
});
