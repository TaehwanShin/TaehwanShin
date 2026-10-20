@EndUserText.label: 'Booking projection'
define view entity ZC_Booking
  as projection on ZI_Booking
{
  key BookingUUID,
      TravelUUID,
      BookingID,
      FlightPrice,
      CurrencyCode,
      _Travel : redirected to parent ZC_Travel
}
