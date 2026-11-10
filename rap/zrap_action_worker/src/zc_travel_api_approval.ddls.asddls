@AccessControl.authorizationCheck: #CHECK
@EndUserText.label: 'Travel - Approval Web API'
define root view entity ZC_Travel_Api_Approval
  provider contract transactional_query
  as projection on ZI_Travel
{
  key TravelUUID,
      TravelID,
      AgencyID,
      CustomerID,
      BeginDate,
      EndDate,
      OverallStatus,
      LocalLastChangedAt
}
