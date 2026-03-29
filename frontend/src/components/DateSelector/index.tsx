import React from 'react';
import { DatePicker } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

interface DateSelectorProps {
  value: string;
  onChange: (date: string) => void;
  style?: React.CSSProperties;
}

/**
 * 日期选择器组件
 */
export const DateSelector: React.FC<DateSelectorProps> = ({ 
  value, 
  onChange, 
  style 
}) => {
  const handleChange = (date: Dayjs | null) => {
    if (date) {
      onChange(date.format('YYYY-MM-DD'));
    }
  };

  return (
    <DatePicker 
      value={dayjs(value)} 
      onChange={handleChange}
      style={{ width: 160, ...style }}
      format="YYYY-MM-DD"
    />
  );
};

export default DateSelector;
