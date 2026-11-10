*"* use this source file for your ABAP unit test classes

CLASS ltc_factory DEFINITION FINAL FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    METHODS creates_worker_per_action FOR TESTING.
ENDCLASS.


CLASS ltc_factory IMPLEMENTATION.

  METHOD creates_worker_per_action.
    cl_abap_unit_assert=>assert_true( xsdbool(
      zcl_trv_action_factory=>create( zif_trv_action=>accept_travel ) IS INSTANCE OF zcl_trv_action_accept ) ).

    cl_abap_unit_assert=>assert_true( xsdbool(
      zcl_trv_action_factory=>create( zif_trv_action=>reject_travel ) IS INSTANCE OF zcl_trv_action_reject ) ).

    cl_abap_unit_assert=>assert_true( xsdbool(
      zcl_trv_action_factory=>create( zif_trv_action=>deduct_discount ) IS INSTANCE OF zcl_trv_action_discount ) ).
  ENDMETHOD.

ENDCLASS.
