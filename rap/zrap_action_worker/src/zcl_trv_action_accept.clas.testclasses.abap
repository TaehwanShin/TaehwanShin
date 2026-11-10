*"* use this source file for your ABAP unit test classes

CLASS ltc_accept DEFINITION FINAL FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    DATA cut TYPE REF TO zif_trv_action.

    METHODS setup.
    METHODS open_travel_becomes_accepted FOR TESTING RAISING zcx_trv_action.
    METHODS non_open_travel_raises       FOR TESTING.
ENDCLASS.


CLASS ltc_accept IMPLEMENTATION.

  METHOD setup.
    cut = NEW zcl_trv_action_accept( ).
  ENDMETHOD.

  METHOD open_travel_becomes_accepted.
    FINAL(changes) = cut->execute( VALUE #( TravelID      = '1'
                                            OverallStatus = zif_trv_action=>status-open ) ).

    cl_abap_unit_assert=>assert_equals( exp = zif_trv_action=>status-accepted
                                        act = changes-OverallStatus ).
    cl_abap_unit_assert=>assert_equals( exp = if_abap_behv=>mk-on
                                        act = changes-%control-OverallStatus ).
  ENDMETHOD.

  METHOD non_open_travel_raises.
    TRY.
        cut->execute( VALUE #( TravelID      = '1'
                               OverallStatus = zif_trv_action=>status-rejected ) ).
        cl_abap_unit_assert=>fail( 'zcx_trv_action expected' ).
      CATCH zcx_trv_action INTO FINAL(error).
        cl_abap_unit_assert=>assert_equals( exp = zcx_trv_action=>not_open
                                            act = error->if_t100_message~t100key ).
    ENDTRY.
  ENDMETHOD.

ENDCLASS.
