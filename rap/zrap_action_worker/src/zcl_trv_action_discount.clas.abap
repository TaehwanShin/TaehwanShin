"! <p class="shorttext synchronized">Worker: deductDiscount (파라미터 action)</p>
CLASS zcl_trv_action_discount DEFINITION
  PUBLIC
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES zif_trv_action.
ENDCLASS.


CLASS zcl_trv_action_discount IMPLEMENTATION.

  METHOD zif_trv_action~execute.
    " param 은 이 action 의 %param (ZA_Discount)
    DATA discount TYPE za_discount.
    discount = param.

    IF discount-discount_percent NOT BETWEEN 1 AND 100.
      RAISE EXCEPTION NEW zcx_trv_action( textid    = zcx_trv_action=>invalid_discount
                                          travel_id = travel-TravelID
                                          percent   = discount-discount_percent ).
    ENDIF.

    changes = VALUE #( %tky                = travel-%tky
                       TotalPrice          = travel-TotalPrice * ( 100 - discount-discount_percent ) / 100
                       %control-TotalPrice = if_abap_behv=>mk-on ).
  ENDMETHOD.

ENDCLASS.
