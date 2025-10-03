import datetime
import pytest
from cogs.graphics_monitor import DateParser, DateParseResult


class TestDateParser:
    """Test suite for DateParser class"""
    
    def test_date_range_format_valid(self):
        """Test valid DD.MM-DD.MM format"""
        # Same month range (note: grace period of 1 day pushes Dec 31 to Jan 1)
        result = DateParser.parse_date("25.12-31.12")
        assert result.original_date_string == "25.12-31.12"
        assert result.expiry_datetime is not None
        # Dec 31 + 1 day grace = Jan 1 of next year
        assert result.expiry_datetime.month == 1
        assert result.expiry_datetime.day == 1
        
        # Cross-month range
        result = DateParser.parse_date("28.02-05.03")
        assert result.original_date_string == "28.02-05.03"
        assert result.expiry_datetime is not None
        
        # Year-spanning range (e.g., December to January)
        result = DateParser.parse_date("25.12-05.01")
        assert result.original_date_string == "25.12-05.01"
        assert result.expiry_datetime is not None
        # Expiry should be in next year
        assert result.expiry_datetime.year == datetime.datetime.now().year + 1
    
    def test_date_range_format_with_text(self):
        """Test date range embedded in larger message"""
        result = DateParser.parse_date("Event happening from 25.12-31.12 come join us!")
        assert result.original_date_string == "25.12-31.12"
        assert result.expiry_datetime is not None
    
    def test_datetime_range_format_valid(self):
        """Test valid DD.MM HH:mm-HH:mm format"""
        result = DateParser.parse_date("15.03 10:00-18:00")
        assert result.original_date_string == "15.03 10:00-18:00"
        assert result.expiry_datetime is not None
        assert result.expiry_datetime.month == 3
        assert result.expiry_datetime.day == 16  # 15th + 1 day grace period
    
    def test_datetime_range_format_with_text(self):
        """Test datetime range embedded in larger message"""
        result = DateParser.parse_date("Sale on 15.03 10:00-18:00 only!")
        assert result.original_date_string == "15.03 10:00-18:00"
        assert result.expiry_datetime is not None
    
    def test_datetime_range_with_spaces_around_dash(self):
        """Test datetime range with spaces around the dash"""
        # Test case from user: "04.10 14:00 - 17:00 🔩"
        result = DateParser.parse_date("04.10 14:00 - 17:00 🔩")
        assert result.original_date_string == "04.10 14:00 - 17:00"
        assert result.expiry_datetime is not None
        
        # Test with various spacing
        result = DateParser.parse_date("04.10 14:00  -  17:00")
        assert result.original_date_string == "04.10 14:00  -  17:00"
        assert result.expiry_datetime is not None
        
        result = DateParser.parse_date("04.10 14:00- 17:00")
        assert result.original_date_string == "04.10 14:00- 17:00"
        assert result.expiry_datetime is not None
    
    def test_date_range_with_spaces_around_dash(self):
        """Test date range with spaces around the dash"""
        result = DateParser.parse_date("25.12 - 31.12")
        assert result.original_date_string == "25.12 - 31.12"
        assert result.expiry_datetime is not None
        
        result = DateParser.parse_date("25.12  -  31.12")
        assert result.original_date_string == "25.12  -  31.12"
        assert result.expiry_datetime is not None
    
    def test_month_name_format_valid(self):
        """Test valid month name formats"""
        # Test a few months (note: grace period adds 1 day after month end)
        result = DateParser.parse_date("january")
        assert result.original_date_string == "January"
        assert result.expiry_datetime is not None
        # Jan 31 + 1 day grace = Feb 1
        assert result.expiry_datetime.month == 2
        assert result.expiry_datetime.day == 1
        
        result = DateParser.parse_date("December")
        assert result.original_date_string == "December"
        assert result.expiry_datetime is not None
        # Dec 31 + 1 day grace = Jan 1 of next year
        assert result.expiry_datetime.month == 1
        assert result.expiry_datetime.day == 1
        
        result = DateParser.parse_date("Available in February")
        assert result.original_date_string == "February"
        assert result.expiry_datetime is not None
    
    def test_month_name_case_insensitive(self):
        """Test that month names are case-insensitive"""
        test_cases = ["january", "January", "JANUARY", "JaNuArY"]
        for test_case in test_cases:
            result = DateParser.parse_date(test_case)
            assert result.original_date_string == "January"
            assert result.expiry_datetime is not None
    
    def test_polish_month_names(self):
        """Test Polish month names"""
        # Test with diacritics
        result = DateParser.parse_date("styczeń")
        assert result.original_date_string == "Styczeń"
        assert result.expiry_datetime is not None
        assert result.expiry_datetime.month == 2  # Jan 31 + 1 day = Feb 1
        
        # Test without diacritics
        result = DateParser.parse_date("styczen")
        assert result.original_date_string == "Styczeń"  # Should normalize to form with diacritics
        assert result.expiry_datetime is not None
        
        # Test Luty (February)
        result = DateParser.parse_date("luty")
        assert result.original_date_string == "Luty"
        assert result.expiry_datetime is not None
        
        # Test Marzec (March)
        result = DateParser.parse_date("marzec")
        assert result.original_date_string == "Marzec"
        assert result.expiry_datetime is not None
        
        # Test Grudzień (December)
        result = DateParser.parse_date("grudzień")
        assert result.original_date_string == "Grudzień"
        assert result.expiry_datetime is not None
        assert result.expiry_datetime.month == 1  # Dec 31 + 1 day = Jan 1
    
    def test_all_polish_months(self):
        """Test all Polish month names"""
        polish_months = [
            ("styczeń", 1), ("luty", 2), ("marzec", 3), ("kwiecień", 4),
            ("maj", 5), ("czerwiec", 6), ("lipiec", 7), ("sierpień", 8),
            ("wrzesień", 9), ("październik", 10), ("listopad", 11), ("grudzień", 12)
        ]
        
        for month_name, month_num in polish_months:
            result = DateParser.parse_date(month_name)
            assert result.original_date_string is not None, f"{month_name} should be recognized"
            assert result.expiry_datetime is not None, f"{month_name} should have an expiry date"
    
    def test_polish_months_without_diacritics(self):
        """Test Polish month names without diacritics (for easier typing)"""
        # Test all months that have alternative spellings without diacritics
        test_cases = [
            ("styczen", "Styczeń"),
            ("kwiecien", "Kwiecień"),
            ("sierpien", "Sierpień"),
            ("wrzesien", "Wrzesień"),
            ("pazdziernik", "Październik"),
            ("grudzien", "Grudzień")
        ]
        
        for input_name, expected_display in test_cases:
            result = DateParser.parse_date(input_name)
            assert result.original_date_string == expected_display, f"{input_name} should normalize to {expected_display}"
            assert result.expiry_datetime is not None
    
    def test_polish_month_case_insensitive(self):
        """Test that Polish month names are case-insensitive"""
        test_cases = ["styczeń", "Styczeń", "STYCZEŃ", "StYcZeŃ"]
        for test_case in test_cases:
            result = DateParser.parse_date(test_case)
            assert result.original_date_string == "Styczeń"
            assert result.expiry_datetime is not None
    
    def test_polish_month_in_sentence(self):
        """Test Polish month names embedded in text"""
        result = DateParser.parse_date("Grafika dostępna w październik")
        assert result.original_date_string == "Październik"
        assert result.expiry_datetime is not None
        
        result = DateParser.parse_date("Sprzedaż trwa przez luty")
        assert result.original_date_string == "Luty"
        assert result.expiry_datetime is not None
    
    def test_invalid_date_format_single_date(self):
        """Test that single date without range is not recognized"""
        # This is the case the user encountered
        result = DateParser.parse_date("01.10")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
    
    def test_invalid_date_format_no_date(self):
        """Test message with no date format"""
        result = DateParser.parse_date("Just some random text without dates")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
    
    def test_invalid_date_format_wrong_delimiter(self):
        """Test dates with wrong delimiters"""
        # Using slashes instead of dots
        result = DateParser.parse_date("01/10-05/10")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
        
        # Using hyphens instead of dots
        result = DateParser.parse_date("01-10-05-10")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
    
    def test_invalid_date_values(self):
        """Test invalid date values that match pattern but are not valid dates"""
        # Invalid month
        result = DateParser.parse_date("15.13-20.13")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
        
        # Invalid day for month
        result = DateParser.parse_date("30.02-31.02")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
    
    def test_grace_period_included(self):
        """Test that 1-day grace period is added to expiry dates"""
        current_year = datetime.datetime.now().year
        
        # Test with date range - should expire on end_date + 1 day at 23:59:59
        result = DateParser.parse_date("01.01-05.01")
        expected_expiry = datetime.datetime(current_year, 1, 6, 23, 59, 59)  # Jan 5 + 1 day
        assert result.expiry_datetime == expected_expiry
        
        # Test with datetime range - should add 1 day to end time
        result = DateParser.parse_date("01.01 10:00-18:00")
        expected_expiry = datetime.datetime(current_year, 1, 2, 18, 0)  # Jan 1 18:00 + 1 day
        assert result.expiry_datetime == expected_expiry
    
    def test_multiple_date_patterns_first_match_wins(self):
        """Test that first matching pattern is used when multiple patterns exist"""
        # This has both a date range and a month name
        result = DateParser.parse_date("Event from 25.12-31.12 in December")
        # Should match the date range pattern first
        assert result.original_date_string == "25.12-31.12"
        # Dec 31 + 1 day grace = Jan 1
        assert result.expiry_datetime.month == 1
        assert result.expiry_datetime.day == 1
    
    def test_edge_case_february_leap_year(self):
        """Test February dates considering leap years"""
        current_year = datetime.datetime.now().year
        is_leap = (current_year % 4 == 0 and current_year % 100 != 0) or (current_year % 400 == 0)
        
        if is_leap:
            # 29.02 should be valid in leap years
            result = DateParser.parse_date("28.02-29.02")
            assert result.expiry_datetime is not None
        else:
            # 29.02 should be invalid in non-leap years
            result = DateParser.parse_date("28.02-29.02")
            # This will fail validation and return None
            assert result.expiry_datetime is None
    
    def test_empty_string(self):
        """Test empty string input"""
        result = DateParser.parse_date("")
        assert result.original_date_string is None
        assert result.expiry_datetime is None
    
    def test_whitespace_only(self):
        """Test whitespace-only input"""
        result = DateParser.parse_date("   \n\t  ")
        assert result.original_date_string is None
        assert result.expiry_datetime is None


class TestDateParserDocumentation:
    """Test that actual behavior matches documented formats"""
    
    def test_documented_example_date_range(self):
        """Test the date range example from SUPPORTED_DATE_FORMATS"""
        result = DateParser.parse_date("25.12-31.12")
        assert result.original_date_string is not None
        assert result.expiry_datetime is not None
    
    def test_documented_example_datetime_range(self):
        """Test the datetime range example from SUPPORTED_DATE_FORMATS"""
        result = DateParser.parse_date("15.03 10:00-18:00")
        assert result.original_date_string is not None
        assert result.expiry_datetime is not None
    
    def test_documented_example_month_names(self):
        """Test that all documented month names work"""
        month_names = ["January", "February", "March", "April", "May", "June",
                      "July", "August", "September", "October", "November", "December"]
        for month in month_names:
            result = DateParser.parse_date(month)
            assert result.original_date_string is not None, f"{month} should be recognized"
            assert result.expiry_datetime is not None, f"{month} should have an expiry date"
    
    def test_documented_example_polish_month_names(self):
        """Test that documented Polish month examples work"""
        # Test the examples mentioned in SUPPORTED_DATE_FORMATS
        result = DateParser.parse_date("Styczeń")
        assert result.original_date_string is not None
        assert result.expiry_datetime is not None
        
        result = DateParser.parse_date("Luty")
        assert result.original_date_string is not None
        assert result.expiry_datetime is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

