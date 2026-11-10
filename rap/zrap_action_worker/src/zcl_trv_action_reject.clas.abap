"! <p class="shorttext synchronized">Worker: rejectTravel</p>
CLASS zcl_trv_action_reject DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES zif_trv_action.
ENDCLASS.


CLASS zcl_trv_action_reject IMPLEMENTATION.

  METHOD zif_trv_action~execute.
    IF travel-OverallStatus <> zif_trv_action=>status-open.
      RAISE EXCEPTION NEW zcx_trv_action( textid    = zcx_trv_action=>not_open
                                          travel_id = travel-TravelID
                                          status    = travel-OverallStatus ).
    ENDIF.

    changes = VALUE #( %tky                   = travel-%tky
                       OverallStatus          = zif_trv_action=>status-rejected
                       %control-OverallStatus = if_abap_behv=>mk-on ).
  ENDMETHOD.

ENDCLASS.
