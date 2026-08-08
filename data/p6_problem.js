/* =====================================================================
   問題6　カデイン法

   ★ 設問はすべて【仮】です。修正案の設計書ができたら文言を差し替えてください。
      行番号と変数名は下のソースコードに合わせて正しく入れてあります。

   このファイルには、左ペインに表示するソースコードと、
   右ペインの設問（Q1〜Q9）が入っています。
   4択問題は p6_quiz.js にあります。

     name   … 書き出しに記録するアルゴリズム名。画面には表示しません
     source … 左ペインに出すソースコード
     steps  … 設問。ブロックの種類は次のとおり
                subhead … 小見出し
                note    … 説明文
                grid    … 表。セルが文字列＝固定表示 / null＝記述欄 /
                          {pre,suf}＝前後の文字つき空欄 / {choice:[…]}＝選択肢
                fill    … 穴埋め文。{b:"キー"}＝空欄、{c:["A","B"]}＝選択肢
                text    … 自由記述欄
                scale   … 5段階の理解度自己評価

   設問が参照する行番号
     6〜8行目   … 配列と current・maximum の初期化
     10〜18行目 … 外側 for 文
     11〜14行目 … current を更新する if / else
     16〜17行目 … maximum を更新する if
     20行目     … 出力処理
   ===================================================================== */
var PROBLEMS = (typeof PROBLEMS !== "undefined" && PROBLEMS) ? PROBLEMS : {};

PROBLEMS["p6"] = {

  name: "カデイン法",

  source: String.raw`#include <stdio.h>
#define SIZE 8

int main(void)
{
    int array[SIZE] = {-2, 1, -3, 4, -1, 2, 1, -5};
    int current = array[0];
    int maximum = array[0];

    for (int i = 1; i < SIZE; i++) {
        if (current + array[i] > array[i])
            current = current + array[i];
        else
            current = array[i];

        if (current > maximum)
            maximum = current;
    }

    printf("最大部分配列の合計：%d\n", maximum);

    return 0;
}`,

  steps: [

    { kind:"intro" },

    /* ------------------------------ Q1 ------------------------------ */
    {
      id:"Q1", title:"Q1　動作例：i = 1 から i = 4 までの値の変化",
      desc:"【仮】処理開始前は current と maximum がどちらも array[0] の値です。10〜18行目について、i = 4 に達するまで追跡してください。記入例の行は採点対象外です。",
      blocks:[
        {
          type:"grid",
          headers:["処理順","i","array[i]","選ばれた式","current","maximum"],
          widths:["12%","10%","14%","28%","18%","18%"],
          rows:[
            {example:true, cells:["記入例","0","-2","（初期値）","-2","-2"]},
            {cells:["1","1", null,null,null,null]},
            {cells:["2","2", null,null,null,null]},
            {cells:["3","3", null,null,null,null]},
            {cells:["4","4", null,null,null,null]}
          ]
        },
        {type:"note", text:"上の表をもとに、次の空欄を埋めてください。"},
        {type:"fill", lead:"【仮】current が更新された回数：", parts:[
          "i = 1 から i = 4 までで、current の値が変わったのは ", {b:"cnt",w:"5em"}, " 回である。"
        ]},
        {type:"fill", lead:"【仮】maximum の変化：", parts:[
          "i = 4 の時点で、maximum は ", {b:"max",w:"5em"}, " になっている。"
        ]},
        {type:"fill", lead:"【仮】式の選ばれ方：", parts:[
          "current + array[i] が array[i] より大きいとき、current には ",
          {b:"pick",w:"12em"}, " が代入される。"
        ]}
      ]
    },

    /* ------------------------------ Q2 ------------------------------ */
    {
      id:"Q2", title:"Q2　各 for 文・if 文の具体的な条件",
      desc:"【仮】コードに書かれている値や条件式を、そのまま読み取って記入してください。目的の説明はまだ不要です。",
      blocks:[
        {type:"subhead", text:"6〜8行目の初期化"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["array に設定される値の個数", null]},
            {cells:["current の最初の値", null]},
            {cells:["maximum の最初の値", null]}
          ]
        },
        {type:"subhead", text:"10行目の for 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["iの最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとのiの更新", null]}
          ]
        },
        {type:"subhead", text:"11〜14行目の if / else"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["比較している2つの式", null]},
            {cells:["条件が成立したとき current に代入する式", null]},
            {cells:["条件が成立しないとき current に代入する式", null]}
          ]
        },
        {type:"subhead", text:"16〜17行目の if"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["判定している条件", null]},
            {cells:["条件が成立したとき maximum に代入する値", null]},
            {cells:["この if で current の値は変わるか", {choice:["変わる","変わらない"]}]}
          ]
        }
      ]
    },

    /* ------------------------------ Q3 ------------------------------ */
    {
      id:"Q3", title:"Q3　変数 current・maximum が保持する値",
      desc:"【仮】コードを確認し、2つの変数がそれぞれ何を保持しているかを記入してください。",
      blocks:[
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["52%","48%"],
          rows:[
            {cells:["SIZEに設定されている値", null]},
            {cells:["配列 array の要素数", null]},
            {cells:["使用できる最大の添字", null]},
            {cells:["7行目の処理後の current の値", null]},
            {cells:["8行目の処理後の maximum の値", null]},
            {cells:["current が表している内容", null]},
            {cells:["maximum が表している内容", null]},
            {cells:["11〜14行目で値が変わる変数", null]},
            {cells:["16〜17行目で値が変わる変数", null]},
            {cells:["ループ中に array の要素は変更されるか", {choice:["変更される","変更されない"]}]},
            {cells:["処理終了後に答えとなる変数", null]}
          ]
        }
      ]
    },

    /* ------------------------------ Q4 ------------------------------ */
    {
      id:"Q4", title:"Q4　コード範囲ごとの処理内容",
      desc:"【仮】処理名を考えるのではなく、指定された行で「何を確認し、どの値を変更するか」を記入してください。",
      blocks:[
        {type:"fill", lead:"6〜8行目：", parts:[
          "array に ", {b:"a1",w:"5em"}, " 個の値を設定し、current と maximum に ",
          {b:"a2",w:"7em"}, " を代入する。"
        ]},
        {type:"fill", lead:"10行目：", parts:[
          "i = ", {b:"b1",w:"4em"}, " から始め、条件 ", {b:"b2",w:"10em"},
          " が成立する間、繰り返す。"
        ]},
        {type:"fill", lead:"11〜14行目：", parts:[
          "current + array[i] と array[i] を比べ、大きいほうを ",
          {b:"c1",w:"7em"}, " に代入する。"
        ]},
        {type:"fill", lead:"16〜17行目：", parts:[
          "current が ", {b:"d1",w:"7em"}, " より大きいとき、",
          {b:"d2",w:"7em"}, " に current を代入する。"
        ]},
        {type:"fill", lead:"処理後の状態：", parts:[
          "ループを1回実行すると、current は ", {b:"e1",w:"16em"}, " を表す値になる。"
        ]}
      ]
    },

    /* ------------------------------ Q5 ------------------------------ */
    {
      id:"Q5", title:"Q5　プログラム全体の仕様",
      desc:"【仮】Q1〜Q4で記入した内容を使い、文章の空欄を埋めてください。1つの長い文章を自由に作る必要はありません。",
      blocks:[
        {type:"subhead", text:"（1）処理対象と目的"},
        {type:"fill", lead:"処理対象：", parts:[
          "このプログラムは、配列 ", {b:"a1",w:"6em"}, " の ", {b:"a2",w:"5em"}, " 個の要素を対象とする。"
        ]},
        {type:"fill", lead:"使用するデータ：", parts:[
          "計算の途中経過は変数 ", {b:"a3",w:"7em"}, " と ", {b:"a4",w:"7em"}, " に保持する。"
        ]},
        {type:"fill", lead:"処理目的：", parts:[
          "配列の中から ", {b:"a5",w:"20em"}, " を求める。"
        ]},

        {type:"subhead", text:"（2）処理方法"},
        {type:"fill", lead:"初期設定：", parts:[
          "current と maximum に ", {b:"b1",w:"7em"}, " を代入する。"
        ]},
        {type:"fill", lead:"繰り返し処理：", parts:[
          "各要素について、current + array[i] と array[i] のうち ",
          {b:"b2",w:"8em"}, " を current とし、current が maximum より大きければ maximum を ",
          {b:"b3",w:"8em"}, " する。"
        ]},

        {type:"subhead", text:"（3）処理終了後の状態"},
        {type:"fill", lead:"maximum の意味：", parts:[
          "処理終了後、maximum は ", {b:"c1",w:"18em"}, " を表す。"
        ]},
        {type:"fill", lead:"current の意味：", parts:[
          "処理終了後、current は ", {b:"c2",w:"18em"}, " を表す。"
        ]},

        {type:"subhead", text:"（4）画面出力"},
        {type:"fill", lead:"出力処理：", parts:[
          "このソースコードには、結果を画面へ出力する処理が ",
          {c:["ある","ない"], key:"d1"}, " 。"
        ]},
        {type:"fill", lead:"出力内容：", parts:[
          "出力されるのは ", {b:"d2",w:"14em"}, " である。"
        ]}
      ]
    },

    /* ------------------------------ Q9 ------------------------------ */
    {
      id:"Q9", title:"Q9　判断に迷った箇所と確信度",
      desc:"コードから判断できなかった箇所、仕様書への書き方に迷った箇所、または設問の意味が分かりにくかった箇所を記述してください。該当する箇所がない場合は「該当なし」と記述してください。",
      blocks:[
        {type:"text", key:"unsure"},
        {type:"note", text:"このプログラムの処理をどの程度理解できたと思いますか。"},
        {type:"scale", key:"confidence"}
      ]
    },

    { kind:"done" }

  ]

};
