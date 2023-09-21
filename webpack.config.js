const path = require('path');
const CssMinimizerPlugin = require('css-minimizer-webpack-plugin');
const MiniCssExtractPlugin = require('mini-css-extract-plugin');
const TerserPlugin = require('terser-webpack-plugin');

module.exports = {
  mode: 'production',
  watch: true,
  watchOptions: {
    poll: 1000, // Check for changes every second
  },
  entry: {
    whg: '/app/whg/webpack/js/whg.js',
    gis_resources: '/app/whg/webpack/js/gis_resources.js'
  },
  output: {
    filename: '[name].bundle.js',
    path: '/app/whg/static/webpack',
  },
  module: {
    rules: [
      {
        test: /\.css$/,
        use: [MiniCssExtractPlugin.loader, 'css-loader'],
      },
      {
        test: /\.scss$/,
        use: [MiniCssExtractPlugin.loader, 'css-loader', 'sass-loader'],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: '[name].bundle.css',
    }),
  ],
  optimization: {
    minimize: false,
    minimizer: [
      new TerserPlugin({
        terserOptions: {
          format: {
            comments: false,
          },
        },
        extractComments: false,
      }), // Minimize JavaScript using TerserPlugin
      new CssMinimizerPlugin(), // Minimize CSS using CssMinimizerPlugin
    ],
  },
};
