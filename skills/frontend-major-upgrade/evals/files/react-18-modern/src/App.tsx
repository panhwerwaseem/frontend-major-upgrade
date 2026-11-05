import { ThemeContext } from './theme';
import SearchBox from './components/SearchBox';
import ThemeBadge from './components/ThemeBadge';

export default function App() {
  return (
    <ThemeContext.Provider value="teal">
      <SearchBox onSearch={(text) => console.log(text)} />
      <ThemeBadge label="Open tickets" />
      <a href="https://example.com/help">Help</a>
    </ThemeContext.Provider>
  );
}
