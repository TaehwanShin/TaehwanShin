*"* use this source file for your ABAP unit test classes

CLASS ltd_worker DEFINITION FINAL FOR TESTING.
  PUBLIC SECTION.
    INTERFACES zif_trv_action.
    DATA mv_called TYPE abap_bool.
ENDCLASS.

CLASS ltd_worker IMPLEMENTATION.
  METHOD zif_trv_action~execute.
    mv_called = abap_true.
  ENDMETHOD.
ENDCLASS.


CLASS ltc_factory DEFINITION FINAL FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    DATA mo_cut TYPE REF TO zcl_trv_action_factory.

    METHODS setup.
    METHODS teardown.

    METHODS creates_registered_worker    FOR TESTING RAISING cx_static_check.
    METHODS action_name_is_case_insens   FOR TESTING RAISING cx_static_check.
    METHODS new_instance_per_create      FOR TESTING RAISING cx_static_check.
    METHODS unknown_action_raises        FOR TESTING.
    METHODS injected_double_is_returned  FOR TESTING RAISING cx_static_check.
    METHODS reset_removes_injection      FOR TESTING RAISING cx_static_check.
    METHODS all_default_actions_present  FOR TESTING.
ENDCLASS.


CLASS ltc_factory IMPLEMENTATION.

  METHOD setup.
    mo_cut = zcl_trv_action_factory=>get_instance( ).
    mo_cut->reset( ).
  ENDMETHOD.

  METHOD teardown.
    mo_cut->reset( ).
  ENDMETHOD.

  METHOD creates_registered_worker.
    DATA(lo_worker) = mo_cut->create( zif_trv_action=>c_action-accept_travel ).
    cl_abap_unit_assert=>assert_true( xsdbool( lo_worker IS INSTANCE OF zcl_trv_action_accept ) ).
  ENDMETHOD.

  METHOD action_name_is_case_insens.
    DATA(lo_worker) = mo_cut->create( 'rejectTravel' ).
    cl_abap_unit_assert=>assert_true( xsdbool( lo_worker IS INSTANCE OF zcl_trv_action_reject ) ).
  ENDMETHOD.

  METHOD new_instance_per_create.
    DATA(lo_first)  = mo_cut->create( zif_trv_action=>c_action-deduct_discount ).
    DATA(lo_second) = mo_cut->create( zif_trv_action=>c_action-deduct_discount ).
    cl_abap_unit_assert=>assert_false( xsdbool( lo_first = lo_second ) ).
  ENDMETHOD.

  METHOD unknown_action_raises.
    TRY.
        mo_cut->create( 'NOSUCHACTION' ).
        cl_abap_unit_assert=>fail( 'zcx_trv_action expected' ).
      CATCH zcx_trv_action INTO DATA(lx_action).
        cl_abap_unit_assert=>assert_equals( act = lx_action->if_t100_message~t100key
                                            exp = zcx_trv_action=>no_worker ).
    ENDTRY.
  ENDMETHOD.

  METHOD injected_double_is_returned.
    DATA(lo_double) = NEW ltd_worker( ).
    mo_cut->inject( iv_action = zif_trv_action=>c_action-accept_travel
                    io_worker = lo_double ).

    DATA(lo_worker) = mo_cut->create( zif_trv_action=>c_action-accept_travel ).
    cl_abap_unit_assert=>assert_true( xsdbool( lo_worker = lo_double ) ).
  ENDMETHOD.

  METHOD reset_removes_injection.
    mo_cut->inject( iv_action = zif_trv_action=>c_action-accept_travel
                    io_worker = NEW ltd_worker( ) ).
    mo_cut->reset( ).

    DATA(lo_worker) = mo_cut->create( zif_trv_action=>c_action-accept_travel ).
    cl_abap_unit_assert=>assert_true( xsdbool( lo_worker IS INSTANCE OF zcl_trv_action_accept ) ).
  ENDMETHOD.

  METHOD all_default_actions_present.
    DATA(lt_actions) = mo_cut->get_registered_actions( ).
    cl_abap_unit_assert=>assert_equals( act = lt_actions
                                        exp = VALUE string_table( ( zif_trv_action=>c_action-accept_travel )
                                                                  ( zif_trv_action=>c_action-deduct_discount )
                                                                  ( zif_trv_action=>c_action-reject_travel )
                                                                  ( zif_trv_action=>c_action-reopen_travel ) ) ).
  ENDMETHOD.

ENDCLASS.
