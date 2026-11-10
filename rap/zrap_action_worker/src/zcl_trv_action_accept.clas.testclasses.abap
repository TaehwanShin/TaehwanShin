*"* use this source file for your ABAP unit test classes

"! 게이트웨이 test double: 메모리 테이블을 BO 처럼 읽고 쓴다. CDS/DB 없이 worker 로직만 검증한다.
CLASS ltd_gateway DEFINITION FINAL FOR TESTING.
  PUBLIC SECTION.
    INTERFACES zif_trv_bo_gateway.
    DATA mt_travels TYPE zif_trv_bo_gateway=>tt_travel.
    DATA mt_updates TYPE zif_trv_bo_gateway=>tt_travel_update.
ENDCLASS.

CLASS ltd_gateway IMPLEMENTATION.

  METHOD zif_trv_bo_gateway~read_travels.
    rt_travels = VALUE #( FOR ls_key    IN it_keys
                          FOR ls_travel IN mt_travels WHERE ( %tky = ls_key-%tky )
                          ( ls_travel ) ).
  ENDMETHOD.

  METHOD zif_trv_bo_gateway~update_travels.
    APPEND LINES OF it_updates TO mt_updates.
    LOOP AT it_updates INTO DATA(ls_update).
      ASSIGN mt_travels[ %tky = ls_update-%tky ] TO FIELD-SYMBOL(<ls_travel>).
      IF sy-subrc <> 0.
        CONTINUE.
      ENDIF.
      IF ls_update-%control-OverallStatus = if_abap_behv=>mk-on.
        <ls_travel>-OverallStatus = ls_update-OverallStatus.
      ENDIF.
      IF ls_update-%control-TotalPrice = if_abap_behv=>mk-on.
        <ls_travel>-TotalPrice = ls_update-TotalPrice.
      ENDIF.
    ENDLOOP.
  ENDMETHOD.

ENDCLASS.


CLASS ltc_accept DEFINITION FINAL FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    CONSTANTS gc_uuid_open     TYPE sysuuid_x16 VALUE '11111111111111111111111111111111'.
    CONSTANTS gc_uuid_accepted TYPE sysuuid_x16 VALUE '22222222222222222222222222222222'.
    CONSTANTS gc_uuid_unknown  TYPE sysuuid_x16 VALUE '99999999999999999999999999999999'.

    TYPES tt_keys   TYPE TABLE FOR ACTION IMPORT zi_travel~acceptTravel.
    TYPES tt_result TYPE TABLE FOR ACTION RESULT zi_travel~acceptTravel.

    DATA mo_cut      TYPE REF TO zif_trv_action.
    DATA mo_gateway  TYPE REF TO ltd_gateway.
    DATA mt_result   TYPE tt_result.
    DATA ms_failed   TYPE zif_trv_bo_gateway=>ts_failed.
    DATA ms_reported TYPE zif_trv_bo_gateway=>ts_reported.

    METHODS setup.
    METHODS run
      IMPORTING it_keys TYPE tt_keys.

    METHODS open_travel_gets_accepted     FOR TESTING.
    METHODS accepted_travel_is_rejected   FOR TESTING.
    METHODS unknown_key_fails_not_found   FOR TESTING.
    METHODS mixed_keys_partial_success    FOR TESTING.
ENDCLASS.


CLASS ltc_accept IMPLEMENTATION.

  METHOD setup.
    mo_gateway = NEW #( ).
    mo_gateway->mt_travels = VALUE #(
      ( TravelUUID = gc_uuid_open     TravelID = '1' OverallStatus = zcl_trv_status_rules=>c_status-open )
      ( TravelUUID = gc_uuid_accepted TravelID = '2' OverallStatus = zcl_trv_status_rules=>c_status-accepted ) ).

    mo_cut = NEW zcl_trv_action_accept( ).
    CLEAR: mt_result, ms_failed, ms_reported.
  ENDMETHOD.

  METHOD run.
    mo_cut->execute( EXPORTING it_keys     = it_keys
                               io_gateway  = mo_gateway
                     CHANGING  ct_result   = mt_result
                               cs_failed   = ms_failed
                               cs_reported = ms_reported ).
  ENDMETHOD.

  METHOD open_travel_gets_accepted.
    run( VALUE #( ( TravelUUID = gc_uuid_open ) ) ).

    cl_abap_unit_assert=>assert_initial( ms_failed-travel ).
    cl_abap_unit_assert=>assert_initial( ms_reported-travel ).

    cl_abap_unit_assert=>assert_equals( act = lines( mo_gateway->mt_updates ) exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = mo_gateway->mt_updates[ 1 ]-OverallStatus
                                        exp = zcl_trv_status_rules=>c_status-accepted ).
    cl_abap_unit_assert=>assert_equals( act = mo_gateway->mt_updates[ 1 ]-%control-OverallStatus
                                        exp = if_abap_behv=>mk-on ).

    cl_abap_unit_assert=>assert_equals( act = lines( mt_result ) exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = mt_result[ 1 ]-%param-OverallStatus
                                        exp = zcl_trv_status_rules=>c_status-accepted ).
  ENDMETHOD.

  METHOD accepted_travel_is_rejected.
    run( VALUE #( ( TravelUUID = gc_uuid_accepted ) ) ).

    cl_abap_unit_assert=>assert_initial( mo_gateway->mt_updates ).
    cl_abap_unit_assert=>assert_initial( mt_result ).

    cl_abap_unit_assert=>assert_equals( act = lines( ms_failed-travel ) exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = lines( ms_reported-travel ) exp = 1 ).
    cl_abap_unit_assert=>assert_bound( ms_reported-travel[ 1 ]-%msg ).
  ENDMETHOD.

  METHOD unknown_key_fails_not_found.
    run( VALUE #( ( TravelUUID = gc_uuid_unknown ) ) ).

    cl_abap_unit_assert=>assert_equals( act = lines( ms_failed-travel ) exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = ms_failed-travel[ 1 ]-%fail-cause
                                        exp = if_abap_behv=>cause-not_found ).
    cl_abap_unit_assert=>assert_initial( mt_result ).
  ENDMETHOD.

  METHOD mixed_keys_partial_success.
    run( VALUE #( ( TravelUUID = gc_uuid_open )
                  ( TravelUUID = gc_uuid_accepted )
                  ( TravelUUID = gc_uuid_unknown ) ) ).

    cl_abap_unit_assert=>assert_equals( act = lines( mo_gateway->mt_updates ) exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = lines( ms_failed-travel )       exp = 2 ).
    cl_abap_unit_assert=>assert_equals( act = lines( mt_result )              exp = 1 ).
    cl_abap_unit_assert=>assert_equals( act = mt_result[ 1 ]-TravelUUID       exp = gc_uuid_open ).
  ENDMETHOD.

ENDCLASS.
