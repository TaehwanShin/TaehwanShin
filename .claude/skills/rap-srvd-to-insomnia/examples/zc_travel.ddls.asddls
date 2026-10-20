@AccessControl.authorizationCheck: #NOT_REQUIRED
@EndUserText.label: 'Travel projection'
@Metadata.allowExtensions: true
define root view entity ZC_Travel
  provider contract transactional_query
  as projection on ZI_Travel
{
  key TravelUUID,
      TravelID,
      @Consumption.valueHelpDefinition: [{ entity: { name: '/DMO/I_Agency', element: 'AgencyID' } }]
      AgencyID,
      CustomerID,
      BeginDate,
      EndDate,
      TotalPrice,
      CurrencyCode,
      OverallStatus,
      LocalLastChangedAt,
      /* associations */
      _Booking : redirected to composition child ZC_Booking,
      _Agency
}
