/* =====================================================================
   問題3　挿入ソート

   ★ 設問はすべて【仮】です。修正案の設計書ができたら文言を差し替えてください。
      行番号と変数名は下のソースコードに合わせて正しく入れてあります。

   このファイルには、左ペインに表示するソースコードと、
   右ペインの設問（Q1〜Q9）が入っています。
   4択問題は p3_quiz.js にあります。

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
     6行目      … 配列の初期化
     8〜18行目  … 外側 for 文
     9〜10行目  … key と j の設定
     12〜15行目 … while 文（後ろへずらす処理）
     17行目     … key の挿入
     20〜25行目 … 出力処理
   ===================================================================== */
var PROBLEMS = (typeof PROBLEMS !== "undefined" && PROBLEMS) ? PROBLEMS : {};

PROBLEMS["p3"] = {

  name: "挿入ソート",

  source: String.raw`#include <stdio.h>
#define SIZE 6

int main(void)
{
    int array[SIZE] = {5, 2, 8, 1, 6, 3};

    for (int i = 1; i < SIZE; i++) {
        int key = array[i];
        int j = i - 1;

        while (j >= 0 && array[j] > key) {
            array[j + 1] = array[j];
            j--;
        }

        array[j + 1] = key;
    }

    printf("ソート結果：");
    for (int i = 0; i < SIZE; i++) {
        printf("%d ", array[i]);
    }

    printf("\n");

    return 0;
}`,

  steps: [

    { kind:"intro" },

    /* ------------------------------ Q1 ------------------------------ */
    {
      id:"Q1", title:"Q1　動作例：i = 2 のときの配列の変化",
      desc:"【仮】処理開始前の配列は {5, 2, 8, 1, 6, 3} です。i = 2 のときの 9〜17行目について、key の挿入が終わるまで追跡してください。記入例の行は採点対象外です。",
      blocks:[
        {
          type:"grid",
          headers:["処理順","j","比較する要素","key と比べた結果","変更する要素","変更後の値"],
          widths:["12%","10%","20%","20%","20%","18%"],
          rows:[
            {example:true, cells:["記入例","1","array[1]","array[1] > key","array[2]","array[1] の値"]},
            {cells:["1","1", null,null,null,null]},
            {cells:["2","0", null,null,null,null]},
            {cells:["3","-1", null,null,null,null]}
          ]
        },
        {type:"note", text:"上の表をもとに、次の空欄を埋めてください。"},
        {type:"fill", lead:"【仮】key の値：", parts:[
          "i = 2 のとき、key に入る値は ", {b:"key",w:"5em"}, " である。"
        ]},
        {type:"fill", lead:"【仮】j の変化：", parts:[
          "j は、1回の処理ごとに ", {b:"step",w:"5em"}, " ずつ変化する。"
        ]},
        {type:"fill", lead:"【仮】挿入位置：", parts:[
          "while 文を抜けたあと、key は array[", {b:"pos",w:"5em"}, "] に代入される。"
        ]}
      ]
    },

    /* ------------------------------ Q2 ------------------------------ */
    {
      id:"Q2", title:"Q2　各 for 文・while 文の具体的な条件",
      desc:"【仮】コードに書かれている値や条件式を、そのまま読み取って記入してください。目的の説明はまだ不要です。",
      blocks:[
        {type:"subhead", text:"8〜18行目の外側 for 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["iの最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとのiの更新", null]},
            {cells:["9行目で key に代入される要素", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["10行目で j に代入される値", null]}
          ]
        },
        {type:"subhead", text:"12〜15行目の while 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["繰り返しを続ける条件", null]},
            {cells:["13行目で値を変更する要素", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["13行目で代入する値", null]},
            {cells:["1回ごとのjの更新", null]},
            {cells:["while 文を抜ける条件", null]}
          ]
        },
        {type:"fill", lead:"【仮】key と while 文の関係：", parts:[
          "while 文は、array[j] が key より ", {b:"cmp",w:"7em"},
          " 間だけ繰り返され、要素を ", {b:"dir",w:"7em"}, " へずらす。"
        ]}
      ]
    },

    /* ------------------------------ Q3 ------------------------------ */
    {
      id:"Q3", title:"Q3　配列 array の範囲と値の変化",
      desc:"【仮】コードを確認し、配列 array の添字の範囲と、各処理で実際に代入される値を記入してください。",
      blocks:[
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["52%","48%"],
          rows:[
            {cells:["SIZEに設定されている値", null]},
            {cells:["配列 array の要素数", null]},
            {cells:["使用できる最小の添字", null]},
            {cells:["使用できる最大の添字", null]},
            {cells:["6行目で array に設定される値", null]},
            {cells:["8行目で i が最初に指す要素", {pre:"array[", suf:"]", w:"6em"}]},
            {cells:["9行目で key に保存される値の意味", null]},
            {cells:["13行目で値が上書きされる要素", {pre:"array[", suf:"]", w:"6em"}]},
            {cells:["13行目の処理で配列の要素数は変わるか", {choice:["変わる","変わらない"]}]},
            {cells:["17行目で key が代入される要素", {pre:"array[", suf:"]", w:"6em"}]},
            {cells:["処理終了後の array の並び順", null]}
          ]
        }
      ]
    },

    /* ------------------------------ Q4 ------------------------------ */
    {
      id:"Q4", title:"Q4　コード範囲ごとの処理内容",
      desc:"【仮】処理名を考えるのではなく、指定された行で「何を確認し、どの値を変更するか」を記入してください。",
      blocks:[
        {type:"fill", lead:"6行目：", parts:[
          "array に ", {b:"a1",w:"14em"}, " の ", {b:"a2",w:"4em"}, " 個の値を設定する。"
        ]},
        {type:"fill", lead:"8〜10行目：", parts:[
          "i = ", {b:"b1",w:"4em"}, " から ", {b:"b2",w:"6em"},
          " まで、key に ", {b:"b3",w:"6em"}, " を、j に ", {b:"b4",w:"6em"}, " を代入する。"
        ]},
        {type:"fill", lead:"12〜15行目：", parts:[
          "条件 ", {b:"c1",w:"14em"}, " が成立する間、array[ j + 1 ] に ",
          {b:"c2",w:"6em"}, " を代入し、j を ", {b:"c3",w:"5em"}, " する。"
        ]},
        {type:"fill", lead:"17行目：", parts:[
          "array[ ", {b:"d1",w:"5em"}, " ] に ", {b:"d2",w:"5em"}, " を代入する。"
        ]},
        {type:"fill", lead:"処理後の状態：", parts:[
          "外側ループを1回実行すると、array[0] から array[ i ] までは ",
          {b:"e1",w:"12em"}, " 状態になる。"
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
          "取り出した値は変数 ", {b:"a3",w:"6em"}, " に一時的に保持する。"
        ]},
        {type:"fill", lead:"処理目的：", parts:[
          "配列の要素を ", {b:"a4",w:"18em"}, " に並べ替える。"
        ]},

        {type:"subhead", text:"（2）処理方法"},
        {type:"fill", lead:"取り出し：", parts:[
          "i 番目の要素を key に取り出し、j に ", {b:"b1",w:"5em"}, " を代入する。"
        ]},
        {type:"fill", lead:"ずらす処理：", parts:[
          "array[j] が key より ", {b:"b2",w:"6em"}, " 間、array[j] を ",
          {b:"b3",w:"8em"}, " へ移し、j を ", {b:"b4",w:"5em"}, " する。"
        ]},
        {type:"fill", lead:"挿入：", parts:[
          "繰り返しを抜けたら、key を array[ ", {b:"b5",w:"5em"}, " ] に入れる。"
        ]},

        {type:"subhead", text:"（3）処理終了後の状態"},
        {type:"fill", lead:"並び順：", parts:[
          "処理終了後、array の要素は ", {b:"c1",w:"14em"}, " に並んでいる。"
        ]},
        {type:"fill", lead:"要素の内容：", parts:[
          "処理の前後で、配列に含まれる値そのものは ", {b:"c2",w:"10em"}, "。"
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
