@AccessControl.authorizationCheck: #CHECK
@EndUserText.label: 'Travel - Pricing Web API'
define root view entity ZC_Travel_Api_Pricing
  provider contract transactional_query
  as projection on ZI_Travel
{
  key TravelUUID,
      TravelID,
      @Semantics.amount.currencyCode: 'CurrencyCode'
      TotalPrice,
      CurrencyCode,
      OverallStatus,
      LocalLastChangedAt
}
