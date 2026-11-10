"! <p class="shorttext synchronized">Travel action worker</p>
"! action 하나 = 이 인터페이스를 구현한 worker 클래스 하나.
"! worker 는 travel 한 건을 받아 "바꿀 값" 만 돌려준다. 읽기/저장(EML)은 handler 가 한다.
INTERFACE zif_trv_action
  PUBLIC.

  TYPES:
    "! factory 에 넘기는 action 식별자
    BEGIN OF ENUM ty_action,
      accept_travel,
      reject_travel,
      deduct_discount,
    END OF ENUM ty_action.

  TYPES ty_travel  TYPE STRUCTURE FOR READ RESULT zi_travel\\Travel.
  TYPES ty_changes TYPE STRUCTURE FOR UPDATE      zi_travel\\Travel.

  CONSTANTS:
    BEGIN OF status,
      open     TYPE zi_travel-OverallStatus VALUE 'O',
      accepted TYPE zi_travel-OverallStatus VALUE 'A',
      rejected TYPE zi_travel-OverallStatus VALUE 'X',
    END OF status.

  "! @parameter travel  | 현재 인스턴스
  "! @parameter param   | action 파라미터(%param). 파라미터 없는 action 은 생략
  "! @parameter changes | 변경할 필드 값 + %control
  "! @raising zcx_trv_action | 업무 오류. handler 가 failed/reported 로 바꾼다
  METHODS execute
    IMPORTING travel         TYPE ty_travel
              param          TYPE any OPTIONAL
    RETURNING VALUE(changes) TYPE ty_changes
    RAISING   zcx_trv_action.

ENDINTERFACE.
