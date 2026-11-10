"! <p class="shorttext synchronized">Worker: acceptTravel</p>
CLASS zcl_trv_action_accept DEFINITION
  PUBLIC
  INHERITING FROM zcl_trv_action_status_base
  FINAL
  CREATE PUBLIC.

  PUBLIC SECTION.
  PROTECTED SECTION.
    METHODS get_target_status REDEFINITION.
  PRIVATE SECTION.
ENDCLASS.


CLASS zcl_trv_action_accept IMPLEMENTATION.

  METHOD get_target_status.
    rv_status = zcl_trv_status_rules=>c_status-accepted.
  ENDMETHOD.

ENDCLASS.
