import { useEffect, useRef } from 'react';

type Props = { onSearch: (text: string) => void; placeholder?: string };

/*
 * History: the class version of this component used a string ref
 * (ref="query", read through this.refs.query) and ReactDOM.findDOMNode(this).
 * Both were replaced with useRef in 2023.
 */
export default function SearchBox({ onSearch, placeholder = 'Search tickets' }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const branch = 'main';

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  return (
    <form
      data-ref="search"
      data-branch={branch}
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(inputRef.current?.value ?? '');
      }}
    >
      <input ref={inputRef} placeholder={placeholder} />
      <button type="submit">Go</button>
    </form>
  );
}
