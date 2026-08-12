/* =====================================================================
   問題C　挿入ソート

   このファイルには、左ペインに表示するソースコードと、
   右ペインの設問（Q1〜Q9）が入っています。
   4択問題は pC_quiz.js にあります。

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
      6行目     … 配列 array の初期値
     10〜24行目 … 外側 for 文
     11〜12行目 … key と j の設定
     16〜19行目 … while 文（要素を右へ移す処理）
     17行目     … array[j + 1] への代入
     23行目     … key の挿入
     出力処理は無い

   ソースコードを差し替えるときは行番号の対応も確認してください。
   ===================================================================== */
var PROBLEMS = (typeof PROBLEMS !== "undefined" && PROBLEMS) ? PROBLEMS : {};

PROBLEMS["pC"] = {

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


    return 0;
}`,

  steps: [

    { kind:"intro" },

    /* ------------------------------ Q1 ------------------------------ */
    {
      id:"Q1", title:"Q1　動作例：i = 3 のときの配列更新",
      desc:"i = 3 の処理開始時点で、array = {2, 5, 8, 1, 6, 3}、key = 1、j = 2 とします。16～23行目について、while文が終了するまで追跡してください。記入例の行は採点対象外です。",
      blocks:[
        {
          type:"grid",
          headers:["処理順","j","比較する値","変更する要素","変更前","変更後","次の j"],
          widths:["13%","10%","16%","19%","13%","13%","16%"],
          rows:[
            {example:true, cells:["記入例","2","8 > 1","array[3]","1","8","1"]},
            {cells:["1", null,null,null,null,null,null]},
            {cells:["2", null,null,null,null,null,null]}
          ]
        },
        {type:"note", text:"上の表をもとに、次の空欄を埋めてください。"},
        {type:"fill", lead:"移動された値：", parts:[
          "while文では、値 ", {b:"v1",w:"4em"}, "、", {b:"v2",w:"4em"}, "、", {b:"v3",w:"4em"},
          " がそれぞれ1つ右の要素へ移される。"
        ]},
        {type:"fill", lead:"jの変化：", parts:[
          "j は、1回の処理ごとに ", {b:"step",w:"4em"}, " ずつ減る。"
        ]},
        {type:"fill", lead:"keyの挿入：", parts:[
          "while文終了後、key = 1 を array[ ", {b:"pos",w:"4em"}, " ] に代入する。"
        ]},
        {type:"fill", lead:"i = 3 の処理終了後の配列：", parts:[
          "{ ", {b:"arr",w:"22em"}, " }"
        ]}
      ]
    },

    /* ------------------------------ Q2 ------------------------------ */
    {
      id:"Q2", title:"Q2　for文・while文の具体的な条件",
      desc:"コードに書かれている値や条件式を、そのまま読み取って記入してください。目的の説明はまだ不要です。",
      blocks:[
        {type:"subhead", text:"10～24行目の外側 for 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["i の最初の値", null]},
            {cells:["繰り返しを続ける条件", null]},
            {cells:["1回ごとの i の更新", null]},
            {cells:["key に代入する値", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["j に最初に代入する値", null]}
          ]
        },
        {type:"subhead", text:"16～19行目の while 文"},
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["44%","56%"],
          rows:[
            {cells:["繰り返しを続ける1つ目の条件", null]},
            {cells:["繰り返しを続ける2つ目の条件", null]},
            {cells:["変更する配列要素", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["その要素に代入する値", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["1回ごとの j の更新", null]}
          ]
        },
        {type:"fill", lead:"2つの繰り返しの関係：", parts:[
          "外側ループの i の値が、key に保存する要素 array[ ", {b:"k1",w:"4em"},
          " ] と、j の最初の値 ", {b:"k2",w:"5em"}, " を決める。"
        ]}
      ]
    },

    /* ------------------------------ Q3 ------------------------------ */
    {
      id:"Q3", title:"Q3　配列 array の範囲と値の変化",
      desc:"コードを確認し、配列arrayの添字範囲と、各処理で実際に代入・移動される値を記入してください。この設問では、まだ「昇順に整列する」という目的は答えなくて構いません。",
      blocks:[
        {
          type:"grid",
          headers:["確認項目","回答"],
          widths:["52%","48%"],
          rows:[
            {cells:["SIZE に設定されている値", null]},
            {cells:["配列 array の要素数", null]},
            {cells:["使用できる最小の添字", null]},
            {cells:["使用できる最大の添字", null]},
            {cells:["外側for文で最初に key に入る値", {pre:"array[1] =", w:"7em"}]},
            {cells:["外側for文で最初に j に入る値", null]},
            {cells:["17行目で値を変更する配列要素", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["17行目でその要素へ代入する値", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["23行目で key を代入する要素", {pre:"array[", suf:"]", w:"7em"}]},
            {cells:["Q1の処理終了後、array[0] の値", null]}
          ]
        }
      ]
    },

    /* ------------------------------ Q4 ------------------------------ */
    {
      id:"Q4", title:"Q4　コード範囲ごとの処理内容",
      desc:"処理名を考えるのではなく、指定された行で「何を比較し、どの値を変更するか」を記入してください。各コード範囲について、指定された空欄だけを埋めてください。",
      blocks:[
        {type:"fill", lead:"10～12行目：", parts:[
          "i = ", {b:"a1",w:"4em"}, " から始め、key に array[ ", {b:"a2",w:"4em"},
          " ] を保存し、j を ", {b:"a3",w:"5em"}, " に設定する。"
        ]},
        {type:"fill", lead:"16～19行目：", parts:[
          "j が ", {b:"b1",w:"4em"}, " 以上かつ array[j]がkeyより ", {b:"b2",w:"6em"},
          " 間、array[j]を array[ ", {b:"b3",w:"5em"}, " ] に代入し、j を ",
          {b:"b4",w:"5em"}, " する。"
        ]},
        {type:"fill", lead:"23行目：", parts:[
          "while文終了後、key を array[ ", {b:"c1",w:"5em"}, " ] に代入する。"
        ]},
        {type:"fill", lead:"外側for文：", parts:[
          "上記の処理を i < ", {b:"d1",w:"5em"}, " の間繰り返し、1回ごとに i を ",
          {b:"d2",w:"4em"}, " 増加させる。"
        ]}
      ]
    },

    /* ------------------------------ Q5 ------------------------------ */
    {
      id:"Q5", title:"Q5　プログラム全体の仕様",
      desc:"Q1～Q4で記入した内容を使い、文章の空欄を埋めてください。1つの長い文章を自由に作る必要はありません。",
      blocks:[
        {type:"subhead", text:"（1）処理対象と目的"},
        {type:"fill", lead:"処理対象：", parts:[
          "このプログラムは、要素数 ", {b:"a1",w:"4em"}, " の整数配列 ", {b:"a2",w:"5em"}, " を対象とする。"
        ]},
        {type:"fill", lead:"処理目的：", parts:[
          "配列内の整数を ", {b:"a3",w:"20em"}, " の順に並べる。"
        ]},

        {type:"subhead", text:"（2）処理方法"},
        {type:"fill", lead:"繰り返し処理：", parts:[
          "i番目の値を ", {b:"b1",w:"5em"}, " に保存し、その値より ", {b:"b2",w:"7em"},
          " 要素を右へ移動した後、keyを空いた位置へ代入する。"
        ]},

        {type:"subhead", text:"（3）処理終了後の状態"},
        {type:"fill", lead:"配列の状態：", parts:[
          "処理終了後、array[0]からarray[SIZE - 1]までの値は ", {b:"c1",w:"14em"},
          " の順に並んでいる。"
        ]},

        {type:"subhead", text:"（4）画面出力"},
        {type:"fill", lead:"出力処理：", parts:[
          "このソースコードには、整列結果を画面へ出力する処理が ",
          {c:["ある","ない"], key:"d1"}, " 。"
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
