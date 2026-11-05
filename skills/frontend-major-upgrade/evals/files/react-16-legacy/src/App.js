import React from 'react';
import ThemeProvider from './components/ThemeProvider';
import SearchBox from './components/SearchBox';
import Badge from './components/Badge';

export default function App() {
  return (
    <ThemeProvider color="teal">
      <SearchBox onSearch={(text) => console.log(text)} />
      <Badge label="New" />
    </ThemeProvider>
  );
}
