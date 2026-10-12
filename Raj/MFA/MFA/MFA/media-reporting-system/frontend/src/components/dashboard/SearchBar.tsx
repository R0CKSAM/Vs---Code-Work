import React from 'react';
import { Search } from 'lucide-react';

interface SearchBarProps {
  query: string;
  onQueryChange: (val: string) => void;
  placeholder?: string;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  query,
  onQueryChange,
  placeholder = 'Search news, advertisements, websites...',
}) => {
  return (
    <div className="search-wrapper">
      <Search size={15} className="search-icon" />
      <input
        type="text"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder={placeholder}
        className="search-input"
      />
      <div className="search-shortcut">⌘K</div>
    </div>
  );
};
