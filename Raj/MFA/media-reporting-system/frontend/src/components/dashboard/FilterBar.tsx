import React from 'react';
import { SlidersHorizontal, RotateCcw } from 'lucide-react';

interface FilterBarProps {
  selectedWebsite: string;
  onSelectWebsite: (val: string) => void;
  selectedSection: string;
  onSelectSection: (val: string) => void;
  selectedDate: string;
  onSelectDate: (val: string) => void;
  selectedContentType: string;
  onSelectContentType: (val: string) => void;
  onReset: () => void;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  selectedWebsite,
  onSelectWebsite,
  selectedSection,
  onSelectSection,
  selectedDate,
  onSelectDate,
  selectedContentType,
  onSelectContentType,
  onReset,
}) => {
  return (
    <div className="filter-bar">
      <div className="filter-group-left">
        <div className="filter-label">
          <SlidersHorizontal size={14} />
          <span>Filters:</span>
        </div>

        <select
          value={selectedWebsite}
          onChange={(e) => onSelectWebsite(e.target.value)}
          className="filter-select"
        >
          <option value="all">All Websites</option>
          <option value="ET BrandEquity">ET BrandEquity</option>
          <option value="Exchange4media">Exchange4media</option>
        </select>

        <select
          value={selectedSection}
          onChange={(e) => onSelectSection(e.target.value)}
          className="filter-select"
        >
          <option value="all">All Sections</option>
          <option value="Digital Advertising">Digital Advertising</option>
          <option value="Broadcasting">Broadcasting</option>
          <option value="Marketing">Marketing</option>
          <option value="Ad Tech">Ad Tech</option>
          <option value="Retail Media">Retail Media</option>
          <option value="Agencies">Agencies</option>
        </select>

        <select
          value={selectedDate}
          onChange={(e) => onSelectDate(e.target.value)}
          className="filter-select"
        >
          <option value="today">Date: Today</option>
          <option value="yesterday">Date: Yesterday</option>
          <option value="last-7-days">Date: Last 7 Days</option>
          <option value="custom">Date: Custom Range...</option>
        </select>

        <select
          value={selectedContentType}
          onChange={(e) => onSelectContentType(e.target.value)}
          className="filter-select"
        >
          <option value="all">Content: All Types</option>
          <option value="articles">Articles</option>
          <option value="advertisements">Advertisements</option>
          <option value="page-changes">Page Changes</option>
        </select>
      </div>

      <button onClick={onReset} className="filter-clear-btn" title="Reset all filters">
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
          <RotateCcw size={11} /> Reset
        </span>
      </button>
    </div>
  );
};
