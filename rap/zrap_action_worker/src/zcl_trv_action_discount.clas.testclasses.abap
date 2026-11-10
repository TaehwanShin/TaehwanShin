*"* use this source file for your ABAP unit test classes

CLASS ltc_discount DEFINITION FINAL FOR TESTING
  DURATION SHORT
  RISK LEVEL HARMLESS.

  PRIVATE SECTION.
    DATA cut TYPE REF TO zif_trv_action.

    METHODS setup.
    METHODS ten_percent_reduces_price FOR TESTING RAISING zcx_trv_action.
    METHODS zero_percent_raises       FOR TESTING.
    METHODS over_100_percent_raises   FOR TESTING.

    METHODS assert_invalid
      IMPORTING percent TYPE za_discount-discount_percent.
ENDCLASS.


CLASS ltc_discount IMPLEMENTATION.

  METHOD setup.
    cut = NEW zcl_trv_action_discount( ).
  ENDMETHOD.

  METHOD ten_percent_reduces_price.
    FINAL(changes) = cut->execute( travel = VALUE #( TravelID = '1'  TotalPrice = 1000 )
                                   param  = VALUE za_discount( discount_percent = 10 ) ).

    cl_abap_unit_assert=>assert_equals( exp = 900
                                        act = changes-TotalPrice ).
    cl_abap_unit_assert=>assert_equals( exp = if_abap_behv=>mk-on
                                        act = changes-%control-TotalPrice ).
  ENDMETHOD.

  METHOD zero_percent_raises.
    assert_invalid( 0 ).
  ENDMETHOD.

  METHOD over_100_percent_raises.
    assert_invalid( 101 ).
  ENDMETHOD.

  METHOD assert_invalid.
    TRY.
        cut->execute( travel = VALUE #( TravelID = '1'  TotalPrice = 1000 )
                      param  = VALUE za_discount( discount_percent = percent ) ).
        cl_abap_unit_assert=>fail( 'zcx_trv_action expected' ).
      CATCH zcx_trv_action INTO FINAL(error).
        cl_abap_unit_assert=>assert_equals( exp = zcx_trv_action=>invalid_discount
                                            act = error->if_t100_message~t100key ).
    ENDTRY.
  ENDMETHOD.

ENDCLASS.
