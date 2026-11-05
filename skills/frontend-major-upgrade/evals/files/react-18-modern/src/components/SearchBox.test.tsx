import { act } from 'react';
import { render, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';

import SearchBox from './SearchBox';

test('submits the typed text', () => {
  const onSearch = vi.fn();
  render(<SearchBox onSearch={onSearch} />);
  const input = screen.getByPlaceholderText('Search tickets') as HTMLInputElement;
  act(() => {
    input.value = 'refund';
    input.form?.requestSubmit();
  });
  expect(onSearch).toHaveBeenCalledWith('refund');
});
