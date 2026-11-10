"! <p class="shorttext synchronized">Travel action worker factory</p>
"! 새 action 을 추가하면 WHEN 한 줄을 추가한다.
CLASS zcl_trv_action_factory DEFINITION
  PUBLIC
  FINAL
  CREATE PRIVATE.

  PUBLIC SECTION.
    CLASS-METHODS create
      IMPORTING action        TYPE zif_trv_action=>ty_action
      RETURNING VALUE(worker) TYPE REF TO zif_trv_action.
ENDCLASS.


CLASS zcl_trv_action_factory IMPLEMENTATION.

  METHOD create.
    worker = SWITCH #( action
                       WHEN zif_trv_action=>accept_travel   THEN NEW zcl_trv_action_accept( )
                       WHEN zif_trv_action=>reject_travel   THEN NEW zcl_trv_action_reject( )
                       WHEN zif_trv_action=>deduct_discount THEN NEW zcl_trv_action_discount( ) ).
  ENDMETHOD.

ENDCLASS.
