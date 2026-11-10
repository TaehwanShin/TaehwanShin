"! <p class="shorttext synchronized">Travel action 업무 오류</p>
"! 메시지 클래스 ZTRV_ACTION
CLASS zcx_trv_action DEFINITION
  PUBLIC
  INHERITING FROM cx_static_check
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
    INTERFACES if_t100_message.

    CONSTANTS:
      "! Travel &1 is not open (status &2)
      BEGIN OF not_open,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '001',
        attr1 TYPE scx_attrname VALUE 'TRAVEL_ID',
        attr2 TYPE scx_attrname VALUE 'STATUS',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF not_open,
      "! Travel &1: discount &2 % is invalid (allowed 1-100)
      BEGIN OF invalid_discount,
        msgid TYPE symsgid      VALUE 'ZTRV_ACTION',
        msgno TYPE symsgno      VALUE '002',
        attr1 TYPE scx_attrname VALUE 'TRAVEL_ID',
        attr2 TYPE scx_attrname VALUE 'PERCENT',
        attr3 TYPE scx_attrname VALUE '',
        attr4 TYPE scx_attrname VALUE '',
      END OF invalid_discount.

    DATA travel_id TYPE zi_travel-TravelID      READ-ONLY.
    DATA status    TYPE zi_travel-OverallStatus READ-ONLY.
    DATA percent   TYPE i                       READ-ONLY.

    METHODS constructor
      IMPORTING textid    LIKE if_t100_message=>t100key
                travel_id TYPE zi_travel-TravelID      OPTIONAL
                status    TYPE zi_travel-OverallStatus OPTIONAL
                percent   TYPE i                       OPTIONAL.
ENDCLASS.


CLASS zcx_trv_action IMPLEMENTATION.

  METHOD constructor ##ADT_SUPPRESS_GENERATION.
    super->constructor( ).
    me->travel_id = travel_id.
    me->status    = status.
    me->percent   = percent.
    if_t100_message~t100key = textid.
  ENDMETHOD.

ENDCLASS.
